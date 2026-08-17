import os

from azure.identity import ClientSecretCredential

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
    GEval,
    ToolCorrectnessMetric,
)
from deepeval.models import AzureOpenAIModel
from deepeval.test_case import LLMTestCaseParams


_credential = ClientSecretCredential(
    tenant_id=os.environ["AZURE_TENANT_ID"],
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"],
)


def _azure_ad_token_provider() -> str:
    return _credential.get_token(
        "https://cognitiveservices.azure.com/.default"
    ).token


judge_model = AzureOpenAIModel(azure_ad_token_provider=_azure_ad_token_provider)

# Keep metrics in one module so eval files stay focused on app execution.
GOLDEN_TABLE_METRICS = [
    AnswerRelevancyMetric(model=judge_model),
    FaithfulnessMetric(model=judge_model),
    ContextualPrecisionMetric(model=judge_model),
    ContextualRecallMetric(model=judge_model),
    ContextualRelevancyMetric(model=judge_model),
    ToolCorrectnessMetric(model=judge_model),
    GEval(
        name="Accuracy",
        criteria="Determine if the 'actual output' is correct and consistent with the 'expected output'.",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.5,
        model=judge_model,
    ),
    GEval(
        name="Completeness",
        criteria="Determine whether the 'actual output' covers all of the key facts, entities, and requirements present in the 'expected output'. A high score means nothing important from the expected output is missing; a low score means the actual output omits significant expected content.",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.5,
        model=judge_model,
    ),
    # Scored on GEval's fixed high-score-is-good convention (success =
    # score >= threshold), so this score is really "groundedness": high
    # means little/no hallucination. The dashboard inverts it (1 - score)
    # before displaying it as a "rate", where low = good.
    GEval(
        name="Hallucination Rate",
        criteria="Determine whether the 'actual output' contains claims, facts, or details that are not supported by or consistent with the 'expected output'. A high score means the actual output is fully grounded in the expected output with no fabricated content; a low score means the actual output contains significant unsupported or fabricated claims.",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.5,
        model=judge_model,
    ),
]
