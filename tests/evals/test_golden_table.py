import pytest

from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.test_case import LLMTestCase

from metrics import GOLDEN_TABLE_METRICS


dataset = EvaluationDataset()
dataset.add_goldens_from_json_file(
    file_path="tests/test_confident/goldens.json"
)


@pytest.mark.parametrize("golden", dataset.goldens)
def test_golden_table(golden: Golden):
    test_case = LLMTestCase(
        input=golden.input,
        actual_output=golden.actual_output,
        expected_output=golden.expected_output,
        context=golden.context,
        retrieval_context=golden.retrieval_context,
        tools_called=golden.tools_called,
        expected_tools=golden.expected_tools,
    )
    assert_test(test_case=test_case, metrics=GOLDEN_TABLE_METRICS)
