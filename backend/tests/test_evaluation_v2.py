import json
import pytest

from backend.utils.evaluation_result import EvaluationResult, FEW_SHOT_EXAMPLE_HIGH_SCORE, FEW_SHOT_EXAMPLE_LOW_SCORE


def test_high_quality_listing_parses_correctly():
    # Use the provided high-quality JSON example
    # find the JSON object portion in the example
    start = FEW_SHOT_EXAMPLE_HIGH_SCORE.find('{')
    text = FEW_SHOT_EXAMPLE_HIGH_SCORE[start:]
    res = EvaluationResult.model_validate_json(text)
    assert res.total_score == 90
    assert res.buy_confidence == 90
    assert res.decision == 'BUY'


def test_low_quality_listing_parses_and_skips():
    start = FEW_SHOT_EXAMPLE_LOW_SCORE.find('{')
    text = FEW_SHOT_EXAMPLE_LOW_SCORE[start:]
    res = EvaluationResult.model_validate_json(text)
    assert res.total_score == 33
    assert res.buy_confidence == 33
    assert res.decision == 'SKIP'
    assert res.improvement_suggestion and len(res.improvement_suggestion) > 10


def test_sum_validator_rejects_bad_total():
    payload = json.loads(FEW_SHOT_EXAMPLE_HIGH_SCORE[FEW_SHOT_EXAMPLE_HIGH_SCORE.find('{'):])
    payload['total_score'] = payload['total_score'] + 10
    with pytest.raises(Exception):
        EvaluationResult.model_validate_json(json.dumps(payload))

