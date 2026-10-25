"""
Adversarial tests for realistic STEM and programming content across Bloom's AI pipelines.
Covers:
- LaTeX math formulas (\\frac{n}{2}, \\log_2(n), \\sum, \\times, \\beta, \\theta, \\nabla)
- Code snippets and programming identifiers (build_heap, linked_list, Python/SQL snippets)
- Quotes, escaped backslashes, Unicode and multiline explanations
- Truncated and empty model responses
- Invalid schemas, duplicate choices, and mismatched correct answers
"""

import json
import pytest
from agents.gap_finder import (
    _sanitize_json_escapes,
    _extract_and_parse_json,
    _validate_question_structure,
    _validate_question_topic_relevance,
    run_diagnostic
)
from agents.recall_loop import generate_recall_prompt
from core.learning import build_practice_set
from services.gemini_service import GeminiService


class MockAdversarialService:
    def __init__(self, raw_response, status="AI-generated"):
        self.raw_response = raw_response
        self.status = status

    def available(self):
        return True

    def generate_text(self, prompt, max_output_tokens=1200, timeout_ms=None):
        return self.raw_response, self.status

    def generate_diagnostic(self, prompt, max_output_tokens=2048, timeout_ms=None):
        return self.raw_response, self.status


# ---------------------------------------------------------------------------
# 1. LaTeX Math Formulas & Equations
# ---------------------------------------------------------------------------

def test_sanitize_preserves_latex_and_parses_json():
    """
    Ensure LaTeX equations with backslashes parse correctly without being corrupted
    into control characters (e.g. \\frac -> \x0crac or \\times -> \times).
    """
    latex_json = r"""
    [
        {
            "prompt": "Evaluate the infinite series \sum_{n=1}^\infty \frac{1}{2^n} \times \log_2(8).",
            "options": ["3", "\frac{3}{2}", "1", "6"],
            "answer": "3",
            "explanation": "The sum is \sum \frac{1}{2^n} = 1, and \log_2(8) = 3, so 1 \times 3 = 3."
        }
    ]
    """
    parsed = _extract_and_parse_json(latex_json)
    assert parsed is not None
    assert len(parsed) == 1
    item = parsed[0]
    assert r"\sum" in item["prompt"]
    assert r"\frac" in item["prompt"]
    assert r"\times" in item["prompt"]
    assert r"\log" in item["prompt"]
    assert item["answer"] == "3"


def test_gap_finder_diagnostic_with_latex_and_code():
    """
    Verify run_diagnostic handles model output containing both
    LaTeX formulas and programming identifiers without failing to parse.
    """
    ai_raw = r"""
    ```json
    [
        {
            "prompt": "In algorithmic analysis of build_heap(arr) for linked_list or array data structures, the time complexity is bounded by \sum_{h=0}^{\lfloor \log_2(n) \rfloor} \frac{n}{2^h} O(h). What is the tight asymptotic bound?",
            "options": ["O(n)", "O(n \log_2(n))", "O(n^2)", "O(\log_2(n))"],
            "answer": "O(n)",
            "explanation": "The Taylor series summation \sum \frac{h}{2^h} converges to 2, yielding O(n) total operations for build_heap.",
            "hint": "Consider the geometric-arithmetic series convergence.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "What is the worst-case comparison count for finding an element in a balanced binary search tree of n nodes?",
            "options": ["O(\log_2(n))", "O(n)", "O(1)", "O(n^2)"],
            "answer": "O(\log_2(n))",
            "explanation": "Tree height is bounded by \log_2(n).",
            "hint": "Height of balanced BST.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Which operation in a Fibonacci heap achieves O(1) amortized time complexity?",
            "options": ["Insert", "Extract-Min", "Delete", "Linear Search"],
            "answer": "Insert",
            "explanation": "Fibonacci heap inserts nodes into root list in O(1) amortized time.",
            "hint": "Lazy consolidation.",
            "mistake_type": "recall"
        }
    ]
    ```
    """
    mock_svc = MockAdversarialService(ai_raw)
    questions, status = run_diagnostic(
        mock_svc,
        subject="Computer Science",
        topic="Data Structures & Heap Construction",
        stage="College",
        count=3
    )

    assert "AI-generated" in status or len(questions) > 0
    assert len(questions) >= 3
    q = questions[0]
    assert "build_heap" in q["prompt"]
    assert r"\sum" in q["prompt"]
    assert q["answer"] == "O(n)"


# ---------------------------------------------------------------------------
# 2. Code Snippets & Multiline Unescaped Strings
# ---------------------------------------------------------------------------

def test_recall_prompt_with_multiline_code_and_newlines():
    """
    Verify generate_recall_prompt parses JSON even when code snippets contain
    raw multiline line breaks.
    """
    raw_ai = """
    ```json
    {
        "challenge": "Implement the core partitioning logic for quicksort on an array.",
        "model_answer": "def partition(arr, low, high):\n    pivot = arr[high]\n    i = low - 1\n    for j in range(low, high):\n        if arr[j] <= pivot:\n            i += 1\n            arr[i], arr[j] = arr[j], arr[i]\n    arr[i + 1], arr[high] = arr[high], arr[i + 1]\n    return i + 1",
        "key_points": [
            "Chosen pivot element",
            "Swapping elements <= pivot",
            "Returning final pivot index"
        ]
    }
    ```
    """
    mock_svc = MockAdversarialService(raw_ai)
    res = generate_recall_prompt(mock_svc, subject="Computer Science", topic="Quicksort Partitioning")
    assert res["source"] == "AI-generated active retrieval"
    assert "def partition" in res["model_answer"]
    assert len(res["key_points"]) == 3


def test_learning_practice_set_with_sql_code():
    """
    Verify build_practice_set successfully parses practice questions containing
    SQL queries and single/double quotes.
    """
    raw_ai = """
    ```json
    [
        {
            "prompt": "Given a relation `Students(id, name, score)`, which SQL query retrieves all students with score > 85?",
            "options": [
                "SELECT * FROM Students WHERE score > 85;",
                "SELECT score FROM Students HAVING score > 85;",
                "FIND ALL FROM Students WHERE score > 85;",
                "FETCH Students WHERE score > 85;"
            ],
            "answer": "SELECT * FROM Students WHERE score > 85;",
            "explanation": "Standard SELECT with WHERE clause filters rows based on column predicate."
        },
        {
            "prompt": "What primary key constraint ensures uniqueness and disallows NULLs?",
            "options": ["PRIMARY KEY", "FOREIGN KEY", "CHECK", "DEFAULT"],
            "answer": "PRIMARY KEY",
            "explanation": "A PRIMARY KEY uniquely identifies each record and enforces NOT NULL."
        },
        {
            "prompt": "Which normal form eliminates partial functional dependencies on candidate keys?",
            "options": ["Second Normal Form (2NF)", "First Normal Form (1NF)", "Third Normal Form (3NF)", "BCNF"],
            "answer": "Second Normal Form (2NF)",
            "explanation": "2NF requires 1NF plus all non-prime attributes to be fully functionally dependent on every candidate key."
        }
    ]
    ```
    """
    mock_svc = MockAdversarialService(raw_ai)
    practice = build_practice_set("Computer Science", "Relational Databases & SQL", gemini=mock_svc)
    assert len(practice) == 3
    assert any("Students" in p["prompt"] for p in practice)
    assert any("SELECT" in p["answer"] for p in practice)
    assert all("id" in p for p in practice)


# ---------------------------------------------------------------------------
# 3. Truncated, Empty, and Malformed Responses
# ---------------------------------------------------------------------------

def test_truncated_json_recovery():
    """
    Verify _extract_and_parse_json recovers complete valid objects from partial/truncated JSON
    where token limits cut off the response.
    """
    truncated_raw = """
    [
        {
            "prompt": "Complete question one on vectors?",
            "options": ["A", "B", "C", "D"],
            "answer": "A",
            "explanation": "Explanation 1"
        },
        {
            "prompt": "Incomplete question two cut off mid-way...
    """
    recovered = _extract_and_parse_json(truncated_raw)
    assert recovered is not None
    assert len(recovered) >= 1
    assert recovered[0]["prompt"] == "Complete question one on vectors?"


def test_empty_and_whitespace_responses():
    """
    Verify empty or whitespace-only model responses gracefully return None without unhandled exceptions.
    """
    assert _extract_and_parse_json("") is None
    assert _extract_and_parse_json("   \n\t  ") is None
    assert _extract_and_parse_json(None) is None


# ---------------------------------------------------------------------------
# 4. Schema Validation & Mismatched Answers
# ---------------------------------------------------------------------------

def test_structure_validation_mismatched_answer():
    """
    Ensure questions where the answer does NOT match any choice in options are rejected.
    """
    bad_item = {
        "prompt": "What is the capital of France?",
        "options": ["Berlin", "Madrid", "Rome", "London"],
        "answer": "Paris",  # Not in options!
        "explanation": "Paris is the capital."
    }
    valid, reason = _validate_question_structure(bad_item)
    assert not valid
    assert "Answer not in options list" in reason


def test_structure_validation_duplicate_choices():
    """
    Ensure questions with duplicate options are rejected.
    """
    bad_item = {
        "prompt": "What is 2 + 2?",
        "options": ["4", "4", "5", "6"],  # Duplicate '4'!
        "answer": "4",
        "explanation": "2 + 2 = 4"
    }
    valid, reason = _validate_question_structure(bad_item)
    assert not valid
    assert "Duplicate choices in options list" in reason


def test_structure_validation_accepts_letter_answer():
    """
    Ensure questions where the model returned answer letter 'B' correctly map to options[1].
    """
    letter_item = {
        "prompt": "Which algorithm is divide-and-conquer?",
        "options": ["Linear Search", "Merge Sort", "Bubble Sort", "Counting Sort"],
        "answer": "B",
        "explanation": "Merge sort divides array into halves."
    }
    valid, reason = _validate_question_structure(letter_item)
    assert valid
    assert letter_item["answer"] == "Merge Sort"


def test_topic_relevance_rejects_irrelevant_hallucination():
    """
    Ensure questions that hallucinate completely unrelated domains (e.g. baking cake
    when requested topic is 'Photosynthesis') are rejected.
    """
    hallucination = {
        "prompt": "How many cups of flour are needed to bake a chocolate cake?",
        "options": ["2 cups", "4 cups", "1 cup", "None"],
        "answer": "2 cups",
        "explanation": "Standard recipe measurement.",
        "hint": "Check baking cookbook."
    }
    relevant, reason = _validate_question_topic_relevance(hallucination, "Photosynthesis", "Biology")
    assert not relevant
    assert "did not address requested topic" in reason
