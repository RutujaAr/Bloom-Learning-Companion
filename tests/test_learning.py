from core.learning import calculate_score, next_review_days, summarize_trends

def test_score():
    assert calculate_score([{"correct": True}, {"correct": False}]) == 50

def test_empty_score():
    assert calculate_score([]) == 0

def test_review_schedule():
    assert next_review_days(False) == 1
    assert next_review_days(True, 0) == 1
    assert next_review_days(True, 1) == 3

def test_summary():
    out = summarize_trends([{"correct": 1}, {"correct": 0}])
    assert out["accuracy"] == 50
    assert out["count"] == 2
