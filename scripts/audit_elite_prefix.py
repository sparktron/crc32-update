"""Audit elite-prefix evidence and completed-budget replay at the frozen commit, not new trials.

Run from the repository root. The audit itself always executes inside a
detached checkout of the run manifest's ``code_commit`` (see
``scripts.frozen_checkout``); only its outputs are copied back.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from optimizer.elite_prefix import (CHECKPOINTS, CHILDREN, LOG, PARENTS, ROOT, algorithm_name,
                                    arms, build_trial, child_spec, run_name)
from optimizer.optimize import independently_check
from verifier.run_formal import run as run_formal
from verifier.verify_network import verification_report, DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED

SCRIPT = Path('scripts/audit_elite_prefix.py')
OUTPUTS = ('validation_summary.json', 'stage1_completed_replay.log', 'stage1_*_verification.json')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def budgets(table):
    """Map each algorithm to its frozen (cap, group, fraction, start, count, parents)."""
    result = {}
    for cap in (7, 6):
        for group, fraction, start, count in arms(cap):
            parents = () if group == 'fresh' else tuple(
                (p['seed'], p['sharing_decisions']) for p in table['caps'][str(cap)][group])
            result[algorithm_name(group, fraction, cap)] = (cap, group, fraction, start, count, parents)
    return result


def replay_incumbent(item):
    record, (cap, group, fraction, start, _, parents) = item
    parent, prefix = child_spec(record['seed'], start, parents, fraction) if parents else (None, 0)
    candidate, _ = build_trial(record['seed'], cap, parent, prefix)
    path = Path(record['artifact'])
    module = 'candidate_' + run_name(group, fraction, cap).removeprefix('stage1_')
    _require(candidate.render(module) == path.read_text(), f'incumbent byte replay failed: {path}')
    metrics = independently_check(candidate).to_dict()
    metrics.pop('unreachable_nodes')
    _require(metrics == record['final_metrics'], f'incumbent metrics differ: {path}')
    return str(path)


def evidence_hashes(names):
    files = [LOG, ROOT / 'run_manifest.json', PARENTS, ROOT / 'stage1_summary.json']
    files += list(CHECKPOINTS.rglob('*.json')) + list(CHECKPOINTS.rglob('*.v'))
    files += [ROOT / f'{name}{suffix}' for name in names for suffix in ('.v', '_diagnostics.jsonl')]
    return {str(p): _sha256(p) for p in sorted(files)}


def proved_targets():
    """Artifacts whose formal acceptance proof appears in the stage progress log."""
    lines = (ROOT / 'stage1_progress.log').read_text().splitlines()
    proved = set()
    for index, line in enumerate(lines):
        if line.startswith('Formal target: '):
            target = line.removeprefix('Formal target: ').rsplit(' (module', 1)[0]
            if any('proved all 32 output comparisons' in later for later in lines[index + 1:index + 4]):
                proved.add(target)
    return proved


def audit():
    manifest = json.loads((ROOT / 'run_manifest.json').read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    _require(head == manifest['code_commit'], 'audit must run at the frozen commit')
    tracked = subprocess.check_output(['git', 'ls-files'], text=True).splitlines()
    _require({p for p in tracked if p.endswith('.py')}
             == {p for p in manifest['source_sha256'] if p.endswith('.py')}, 'frozen source set differs')
    for path, digest in manifest['source_sha256'].items():
        _require(_sha256(path) == digest, f'frozen source differs: {path}')
    table = json.loads(PARENTS.read_text())
    frozen = budgets(table)
    records = [json.loads(line) for line in LOG.read_text().splitlines() if line]
    _require(len({r['attempt_id'] for r in records}) == len(records), 'duplicate attempt IDs')
    counts, names = {}, []
    for algorithm, (cap, group, fraction, start, count, parents) in frozen.items():
        name = run_name(group, fraction, cap)
        selected = [r for r in records if r['algorithm'] == algorithm]
        diagnostics = [json.loads(line) for line in
                       (ROOT / f'{name}_diagnostics.jsonl').read_text().splitlines()]
        expected = list(range(start, start + count))
        _require([r['seed'] for r in selected] == expected
                 and [d['seed'] for d in diagnostics] == expected, f'{name} coverage differs')
        for r, d in zip(selected, diagnostics):
            m = r['final_metrics']
            _require(r['verification_passed'] and m['maximum_depth'] <= cap, f'{name} trial invalid')
            _require(m['xor2_count'] == d['xor2_count'] == d['sharing_retained'] + d['finishing_retained'],
                     f'{name} phase gate accounting differs')
            _require(min(d['remaining_kraft_budget']) >= 0 and r['runtime_seconds'] > 0,
                     f'{name} Kraft budget or runtime invalid')
            parent, prefix = child_spec(r['seed'], start, parents, fraction) if parents else (None, 0)
            digest = None if parent is None else table['caps'][str(cap)][group][
                (r['seed'] - start) // CHILDREN]['prefixes'][str(fraction)]['state_sha256']
            _require(d['parent_seed'] == parent and d['prefix_decisions'] == prefix
                     and prefix <= d['sharing_decisions'] and d['prefix_state_sha256'] == digest,
                     f'{name} prefix replay differs at seed {r["seed"]}')
        counts[name] = count
        names.append(name)
    _require(sum(counts.values()) == len(records), 'unexpected trial outside frozen budgets')
    accepted = [r for r in records if r['accepted']]
    proved = proved_targets()
    _require(all(any(t == r['artifact'] or t.endswith('/' + r['artifact']) for t in proved)
                 for r in accepted), 'an accepted incumbent lacks a formal proof trace')
    with ProcessPoolExecutor(max_workers=16) as pool:
        replayed = list(pool.map(replay_incumbent, [(r, frozen[r['algorithm']]) for r in accepted]))
    before = evidence_hashes(names)
    with (ROOT / 'stage1_completed_replay.log').open('w') as stream:
        subprocess.run(['python3', '-B', '-m', 'optimizer.elite_prefix', '--stage', 'stage1',
                        '--workers', '16'], stdout=stream, stderr=subprocess.STDOUT, check=True)
    after = evidence_hashes(names)
    _require(before == after, 'completed-budget replay changed evidence')
    reports = {}
    for name in names:
        path = ROOT / f'{name}.v'
        report = verification_report(path, DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED)
        run_formal(path)
        out = ROOT / f'{name}_verification.json'
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        reports[str(path)] = str(out)
    validation = {
        'code_commit': manifest['code_commit'], 'counts': counts,
        'unique_trials': len(records), 'fully_verified_incumbent_acceptances': len(accepted),
        'incumbents_replayed_byte_identically': replayed,
        'acceptance_formal_trace_passed': True, 'prefix_digests_passed': True,
        'completed_replay_unchanged_files': len(before), 'evidence_sha256': after,
        'source_identity_passed': True, 'raw_invariants_passed': True,
        'best_artifact_verification_reports': reports,
    }
    (ROOT / 'validation_summary.json').write_text(json.dumps(validation, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in validation.items()
                      if k not in ('evidence_sha256', 'incumbents_replayed_byte_identically')},
                     sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', action='store_true', help=argparse.SUPPRESS)
    if parser.parse_args().frozen:
        audit()
        return
    # The frozen commit predates this script and the helper; copy the script in.
    from scripts.frozen_checkout import run_frozen
    manifest = json.loads((ROOT / 'run_manifest.json').read_text())
    run_frozen(manifest['code_commit'], [LOG, ROOT, CHECKPOINTS, SCRIPT],
               ['python3', '-B', '-m', 'scripts.audit_elite_prefix', '--frozen'],
               [str(ROOT / name) for name in OUTPUTS])


if __name__ == '__main__':
    main()
