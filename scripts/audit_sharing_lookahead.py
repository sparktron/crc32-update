"""Audit frozen experiment evidence and completed-budget replay, not new trials."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from optimizer.optimize import independently_check
from optimizer.sharing_lookahead import (
    CHECKPOINTS, LOG, ROOT, SEEDS, algorithm_name, build_trial,
)
from verifier.run_formal import run as run_formal
from verifier.verify_network import verification_report, DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED


def replay_incumbent(record):
    cap = record['parameters']['depth_cap']
    arm = 'candidate' if '-candidate-' in record['algorithm'] else 'control'
    candidate, _ = build_trial(record['seed'], cap, arm)
    path = Path(record['artifact'])
    if candidate.render(f'candidate_lookahead_{arm}_depth{cap}') != path.read_text():
        raise ValueError(f'incumbent byte replay failed: {path}')
    metrics = independently_check(candidate).to_dict()
    metrics.pop('unreachable_nodes')
    if metrics != record['final_metrics']:
        raise ValueError('incumbent metrics differ')
    return str(path)


def evidence_hashes():
    files = [LOG, ROOT / 'run_manifest.json']
    files += list(CHECKPOINTS.rglob('*.json')) + list(CHECKPOINTS.rglob('*.v'))
    files += list(ROOT.glob('stage*.json')) + list(ROOT.glob('stage*.jsonl')) + list(ROOT.glob('stage*.v'))
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def main():
    manifest = json.loads((ROOT / 'run_manifest.json').read_text())
    for path, digest in manifest['source_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError(f'frozen source differs: {path}')
        committed = subprocess.check_output(['git', 'show', f"{manifest['code_commit']}:{path}"])
        if hashlib.sha256(committed).hexdigest() != digest:
            raise ValueError('source does not match preregistration commit')
    records = [json.loads(line) for line in LOG.read_text().splitlines()]
    if len({r['attempt_id'] for r in records}) != len(records):
        raise ValueError('duplicate attempt IDs')
    counts = {}
    for stage in ('stage1', 'stage2'):
        summary = json.loads((ROOT / f'{stage}_summary.json').read_text())
        for cap_string in summary['caps']:
            cap = int(cap_string)
            start, count = SEEDS[stage, cap]
            for arm in ('control', 'candidate'):
                run = f'{stage}_{arm}_depth{cap}'
                selected = [r for r in records if r['algorithm'] == algorithm_name(arm, cap)
                            and start <= r['seed'] < start + count]
                diagnostics = [json.loads(line) for line in
                               (ROOT / f'{run}_diagnostics.jsonl').read_text().splitlines()]
                expected = list(range(start, start + count))
                if [r['seed'] for r in selected] != expected or [r['seed'] for r in diagnostics] != expected:
                    raise ValueError('coverage differs')
                for r, d in zip(selected, diagnostics):
                    m = r['final_metrics']
                    assert r['verification_passed'] and m['maximum_depth'] <= cap
                    assert m['xor2_count'] == d['xor2_count'] == d['sharing_retained'] + d['finishing_retained']
                    assert min(d['remaining_kraft_budget']) >= 0
                    assert r['runtime_seconds'] > 0
                counts[run] = count
    if sum(counts.values()) != len(records):
        raise ValueError('unexpected trial outside frozen budgets')
    accepted = [r for r in records if r['accepted']]
    with ProcessPoolExecutor(max_workers=16) as pool:
        replayed = list(pool.map(replay_incumbent, accepted))
    before = evidence_hashes()
    for stage in ('stage1', 'stage2'):
        with (ROOT / f'{stage}_completed_replay.log').open('w') as stream:
            subprocess.run(['python3', '-B', '-m', 'optimizer.sharing_lookahead',
                            '--stage', stage, '--workers', '16'], stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
    after = evidence_hashes()
    if before != after:
        raise ValueError('completed-budget replay changed evidence')
    reports = {}
    for path in sorted(ROOT.glob('stage*.v')):
        report = verification_report(path, DEFAULT_RANDOM_TESTS, DEFAULT_RANDOM_SEED)
        run_formal(path)
        out = path.with_name(path.stem + '_verification.json')
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        reports[str(path)] = str(out)
    validation = {
        'code_commit': manifest['code_commit'], 'counts': counts,
        'unique_trials': len(records), 'fully_verified_incumbent_acceptances': len(accepted),
        'incumbents_replayed_byte_identically': replayed,
        'completed_replay_unchanged_files': len(before), 'evidence_sha256': after,
        'source_identity_passed': True, 'raw_invariants_passed': True,
        'best_artifact_verification_reports': reports,
    }
    (ROOT / 'validation_summary.json').write_text(json.dumps(validation, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in validation.items() if k != 'evidence_sha256'}, sort_keys=True))


if __name__ == '__main__':
    main()
