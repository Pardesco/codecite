from pathlib import Path

from codeplumb.evaluate import load_golden, render_report, run_eval

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "sample-bc.yaml"


def test_eval_hybrid_meets_gate(db):
    conn, emb = db
    golden = load_golden(GOLDEN)
    assert len(golden) >= 60
    results = run_eval(conn, emb, golden, ["naive", "hybrid", "lexical", "vector"])
    md = render_report(results)
    assert "| hybrid |" in md
    s = results["hybrid"]["summary"]
    # fake (hashed bag-of-words) embedder; the real model should do better, never worse
    assert s["hit@5"] >= 0.85, md
    assert s["mrr"] >= 0.6, md
    assert s["abstain"] >= 0.5, md  # hashed-BoW similarities overlap; tune per real model
    assert s["false_abstain"] <= 0.15, md
    assert results["naive"]["summary"]["hit@5"] < s["hit@5"], md  # section chunking must beat fixed windows
