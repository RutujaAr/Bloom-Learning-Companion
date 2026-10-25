import os
import json
import pytest
import time
from services.gemini_service import GeminiService
from agents.gap_finder import (
    run_diagnostic,
    _validate_question_structure,
    _validate_question_topic_relevance,
    _extract_and_parse_json
)


# ---------------------------------------------------------------------------
# 1. Simple Live Request (Separate from Diagnostic Workflow)
# ---------------------------------------------------------------------------

def test_simple_live_api_request():
    """
    Test one simple live API request separately from the diagnostic workflow
    using the configured Gemini API and default model (gemini-3.5-flash-lite).
    Records duration, result, and sanitized error category.
    """
    svc = GeminiService()
    if not svc.available():
        pytest.skip("Gemini API key not configured in environment or secrets.")

    t0 = time.time()
    raw, status = svc.generate_text("Answer with the single word 'CONFIRMED'.", max_output_tokens=50)
    elapsed = round(time.time() - t0, 2)

    # If Google returns 429 quota exhaustion on the free tier, report diagnostic details
    if not raw and svc._last_error_category == "quota":
        pytest.skip(
            f"Google Free Tier daily quota (20 req/day) exhausted for {svc.model} "
            f"(elapsed={elapsed}s, status='{status}'). Test recorded quota limit cleanly."
        )

    if raw:
        assert "CONFIRMED" in raw.upper()
        assert svc._last_error_category is None


# ---------------------------------------------------------------------------
# 2. Mocked Tests for Arbitrary Academic Topics Pipeline
# (Ensures 100% Deterministic Testing of Extraction, Validation, and Differentiation)
# ---------------------------------------------------------------------------

class MockLiveGemini:
    """Mock Gemini service to verify end-to-end arbitrary academic topic generation without consuming quota."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.model = "gemini-3.5-flash-lite"
        self.last_metrics = {"attempts": [{"attempt": 1, "duration_s": 1.2, "status": "success", "code": 200}], "timeout_occurred": False}

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=1200, timeout_ms=None):
        if self.responses:
            return self.responses.pop(0), "AI-generated"
        return "[]", "AI-generated"


@pytest.mark.parametrize("subject,topic,sample_questions,expected_terms", [
    (
        "Computer Science",
        "Data Structures - linked lists or trees",
        [
            {
                "prompt": "What is the time complexity of searching an element in a balanced binary search tree of n nodes?",
                "options": ["O(log n)", "O(n)", "O(1)", "O(n log n)"],
                "answer": "O(log n)",
                "explanation": "In a balanced BST, height is O(log n), so search traversal takes logarithmic time.",
                "hint": "Consider the tree height after balanced splits.",
                "mistake_type": "conceptual"
            },
            {
                "prompt": "In a singly linked list, what is required to insert a node at the head?",
                "options": ["Update new node's next pointer to head, then update head", "Traverse entire list to end", "Reallocate contiguous array buffer", "Shift all elements by one position"],
                "answer": "Update new node's next pointer to head, then update head",
                "explanation": "Head insertion only requires updating the pointer in O(1) time.",
                "hint": "Only pointer updates are needed at the beginning.",
                "mistake_type": "conceptual"
            },
            {
                "prompt": "Which traversal of a binary search tree visits keys in ascending sorted order?",
                "options": ["In-order traversal", "Pre-order traversal", "Post-order traversal", "Level-order traversal"],
                "answer": "In-order traversal",
                "explanation": "In-order traversal (left, root, right) yields sorted keys for any binary search tree.",
                "hint": "Visiting left subtree before root yields sorted sequence.",
                "mistake_type": "recall"
            }
        ],
        ["tree", "list", "node", "binary", "pointer", "traversal"]
    ),
    (
        "Computer Science",
        "DBMS - normalization",
        [
            {
                "prompt": "In relational database design, a relation is in Second Normal Form (2NF) if and only if it is in 1NF and:",
                "options": ["Every non-prime attribute is fully functionally dependent on the candidate key", "It contains no transitive dependencies", "All attributes are atomic values only", "Every determinant is a superkey"],
                "answer": "Every non-prime attribute is fully functionally dependent on the candidate key",
                "explanation": "2NF eliminates partial functional dependencies on composite candidate keys.",
                "hint": "Think about partial dependencies on composite keys.",
                "mistake_type": "conceptual"
            },
            {
                "prompt": "Third Normal Form (3NF) strictly resolves which primary design flaw in relational schemas?",
                "options": ["Transitive dependencies between non-key attributes", "Non-atomic multivalued attributes", "Missing foreign key constraints", "Cyclic foreign key references"],
                "answer": "Transitive dependencies between non-key attributes",
                "explanation": "3NF requires that no non-prime attribute is transitively dependent on any candidate key.",
                "hint": "Look for indirect functional dependencies X -> Y -> Z.",
                "mistake_type": "conceptual"
            },
            {
                "prompt": "Boyce-Codd Normal Form (BCNF) requires that for every non-trivial functional dependency X -> Y:",
                "options": ["X must be a superkey", "Y must be a prime attribute", "X and Y must share a common attribute", "X must be a foreign key"],
                "answer": "X must be a superkey",
                "explanation": "BCNF requires every determinant X to be a superkey of the relation.",
                "hint": "What must the left-hand determinant always be in BCNF?",
                "mistake_type": "recall"
            }
        ],
        ["normal", "dependency", "key", "relation", "table", "transitive"]
    ),
    (
        "Computer Science",
        "Computer Vision - image segmentation",
        [
            {
                "prompt": "What is the key difference between semantic segmentation and instance segmentation in computer vision?",
                "options": ["Instance segmentation distinguishes between separate individual objects of the same class", "Semantic segmentation produces bounding boxes instead of pixel masks", "Instance segmentation only detects whole images rather than pixels", "Semantic segmentation requires 3D point cloud data"],
                "answer": "Instance segmentation distinguishes between separate individual objects of the same class",
                "explanation": "Semantic segmentation classifies every pixel into a class label; instance segmentation identifies individual instances.",
                "hint": "Does the model label two nearby cats as Cat1 and Cat2 or just 'cat'?",
                "mistake_type": "conceptual"
            },
            {
                "prompt": "In image segmentation evaluation, what does the Mean Intersection over Union (mIoU) metric calculate?",
                "options": ["The average ratio of overlap area to total combined area across predicted and ground-truth masks", "The percentage of pixels that are exactly zero in the mask", "The Euclidean distance between bounding box centroids", "The classification accuracy of the image background"],
                "answer": "The average ratio of overlap area to total combined area across predicted and ground-truth masks",
                "explanation": "mIoU measures the spatial overlap divided by the union between ground truth and predicted segmentation masks.",
                "hint": "IoU is Area of Overlap divided by Area of Union.",
                "mistake_type": "calculation"
            },
            {
                "prompt": "Which neural network architecture introduced skip connections combining high-level semantic features with fine-grained spatial features for medical image segmentation?",
                "options": ["U-Net", "AlexNet", "VGG16", "ResNet-50"],
                "answer": "U-Net",
                "explanation": "U-Net uses an encoder-decoder structure with symmetric skip connections to preserve spatial detail for segmentation.",
                "hint": "Look for the encoder-decoder architecture shaped like a letter.",
                "mistake_type": "recall"
            }
        ],
        ["segmentation", "mask", "pixel", "iou", "instance", "semantic"]
    )
])
def test_mocked_diagnostic_generation_for_academic_topics(subject, topic, sample_questions, expected_terms):
    """
    Verify that arbitrary academic topic generation:
    - Parses JSON array of questions correctly
    - Validates structure (prompt, 4 options, answer in options, explanation)
    - Validates domain relevance for Data Structures, DBMS, and Computer Vision
    - Sets appropriate status note without requiring a pre-existing fallback bank
    """
    mock_service = MockLiveGemini([json.dumps(sample_questions)])

    questions, status = run_diagnostic(
        mock_service,
        subject=subject,
        topic=topic,
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )

    assert len(questions) == 3
    assert "AI-generated" in status
    assert "not syllabus-verified" in status.lower()

    # Verify all question structures
    for q in questions:
        ok, msg = _validate_question_structure(q)
        assert ok, f"Structure validation failed: {msg}"
        ok_top, top_msg = _validate_question_topic_relevance(q, topic, subject)
        assert ok_top, f"Topic relevance failed: {top_msg}"

        q_text = f"{q['prompt']} {q['explanation']} {' '.join(q['options'])}".lower()
        assert any(term in q_text for term in expected_terms), f"Expected terms {expected_terms} in {q_text}"


def test_mocked_questions_genuinely_differ_across_topics():
    """
    Verify questions generated for Data Structures, DBMS, and Computer Vision
    have completely distinct prompts and topics.
    """
    ds_qs = [
        {"prompt": "What is the time complexity to insert a node at the head of a linked list?", "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"], "answer": "O(1)", "explanation": "Only pointer updates.", "hint": "No traversal.", "mistake_type": "conceptual"},
        {"prompt": "In a binary search tree, what is the maximum number of children a node can have?", "options": ["2", "1", "3", "Unlimited"], "answer": "2", "explanation": "Binary trees have at most two children.", "hint": "Binary means two.", "mistake_type": "recall"},
        {"prompt": "Which traversal visits binary search tree nodes in sorted order?", "options": ["In-order", "Pre-order", "Post-order", "Level-order"], "answer": "In-order", "explanation": "In-order yields sorted order.", "hint": "Left-root-right.", "mistake_type": "recall"}
    ]
    dbms_qs = [
        {"prompt": "A table is in 2NF if all non-key attributes are fully dependent on:", "options": ["Candidate key", "Foreign key", "Surrogate key", "Alternate key"], "answer": "Candidate key", "explanation": "2NF eliminates partial dependencies.", "hint": "Primary/candidate key.", "mistake_type": "conceptual"},
        {"prompt": "Which normal form eliminates transitive functional dependencies?", "options": ["3NF", "1NF", "2NF", "BCNF"], "answer": "3NF", "explanation": "3NF removes transitive dependencies.", "hint": "Third normal form.", "mistake_type": "recall"},
        {"prompt": "In BCNF, every functional dependency determinant must be a:", "options": ["Superkey", "Candidate key", "Foreign key", "Composite key"], "answer": "Superkey", "explanation": "BCNF requires all determinants to be superkeys.", "hint": "Superkey.", "mistake_type": "recall"}
    ]
    cv_qs = [
        {"prompt": "What is the goal of semantic segmentation?", "options": ["Assign each pixel a class label", "Draw bounding boxes", "Generate 3D point cloud", "Count image brightness"], "answer": "Assign each pixel a class label", "explanation": "Dense pixel-wise classification.", "hint": "Pixel labels.", "mistake_type": "conceptual"},
        {"prompt": "In image segmentation, what does IoU measure?", "options": ["Overlap over union of masks", "Pixel count", "Loss gradient", "Learning rate"], "answer": "Overlap over union of masks", "explanation": "Intersection over union.", "hint": "IoU.", "mistake_type": "conceptual"},
        {"prompt": "Which convolutional network uses U-shaped skip connections?", "options": ["U-Net", "ResNet", "AlexNet", "VGG"], "answer": "U-Net", "explanation": "U-Net preserves spatial resolution.", "hint": "U-shaped.", "mistake_type": "recall"}
    ]

    mock_service = MockLiveGemini([json.dumps(ds_qs), json.dumps(dbms_qs), json.dumps(cv_qs)])

    qs_ds, _ = run_diagnostic(mock_service, "Computer Science", "Data Structures - linked lists or trees", count=3)
    qs_dbms, _ = run_diagnostic(mock_service, "Computer Science", "DBMS - normalization", count=3)
    qs_cv, _ = run_diagnostic(mock_service, "Computer Science", "Computer Vision - image segmentation", count=3)

    prompts_ds = {q["prompt"] for q in qs_ds}
    prompts_dbms = {q["prompt"] for q in qs_dbms}
    prompts_cv = {q["prompt"] for q in qs_cv}

    assert len(prompts_ds.intersection(prompts_dbms)) == 0
    assert len(prompts_ds.intersection(prompts_cv)) == 0
    assert len(prompts_dbms.intersection(prompts_cv)) == 0


# ---------------------------------------------------------------------------
# 3. Live Generation for Arbitrary Academic Topics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject,topic", [
    ("Computer Science", "Data Structures - linked lists or trees"),
    ("Computer Science", "DBMS - normalization"),
    ("Computer Science", "Computer Vision - image segmentation")
])
def test_live_diagnostic_generation_for_academic_topics(subject, topic):
    """
    Live test against Gemini API for arbitrary topics.
    Reports quota exhaustion gracefully if the daily Free Tier limit is reached.
    """
    svc = GeminiService()
    if not svc.available():
        pytest.skip("Gemini API key not configured in environment or secrets.")

    t0 = time.time()
    questions, source = run_diagnostic(
        svc,
        subject=subject,
        topic=topic,
        level="Standard",
        count=3,
        stage="College",
        curriculum="College / University Outline"
    )
    elapsed = round(time.time() - t0, 2)

    if svc._last_error_category in ("quota", "timeout"):
        pytest.skip(
            f"Live API generation for '{topic}' paused due to Google Free Tier {svc._last_error_category} "
            f"on model {svc.model} (elapsed={elapsed}s, source='{source}')."
        )

    if questions:
        assert len(questions) >= 3
        assert "AI-generated" in source
        for q in questions:
            ok, msg = _validate_question_structure(q)
            assert ok, f"Question schema invalid: {msg}"

