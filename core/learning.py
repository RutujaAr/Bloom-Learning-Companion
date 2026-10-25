import json
import re
from uuid import uuid4
from datetime import date, timedelta

MISTAKE_TAXONOMY = {
    "conceptual": "Conceptual clarity",
    "calculation": "Calculation accuracy",
    "careless": "Calculation accuracy",
    "misread": "Question interpretation",
    "incomplete": "Answer completeness",
    "recall": "Active recall"
}

def calculate_score(results):
    if not results:
        return 0
    return round(sum(1 for r in results if r.get("correct")) / len(results) * 100)

def summarize_trends(attempts):
    if not attempts:
        return {"accuracy": 0, "count": 0}
    return {"accuracy": round(sum(int(bool(a.get("correct"))) for a in attempts) / len(attempts) * 100), "count": len(attempts)}

def next_review_days(correct, streak=0):
    if not correct:
        return 1
    schedule = [1, 3, 7, 14, 30]
    idx = max(0, min(int(streak), len(schedule) - 1))
    return schedule[idx]

def build_practice_set(subject, topic, analysis=None, gemini=None, stage=None, curriculum=None, curriculum_context=None, custom_syllabus=""):
    """Generate 3 targeted practice questions addressing the student's identified gaps, calibrated to their education stage."""
    mistakes = []
    if analysis and isinstance(analysis, dict):
        mistakes = analysis.get("mistakes", [])

    mistake_types = [m.get("type", "conceptual") for m in mistakes if isinstance(m, dict)]
    primary_mistake = mistake_types[0] if mistake_types else "conceptual"

    # Attempt AI generation if Gemini is available
    if gemini and getattr(gemini, "available", lambda: False)():
        from core.syllabus import build_curriculum_context
        ctx = curriculum_context or build_curriculum_context(stage, curriculum, subject, topic, custom_syllabus=custom_syllabus)
        prompt = f"""You are an educational assistant creating targeted practice questions.
{ctx}

Create exactly 3 multiple-choice practice questions targeting the student's weak areas in:
Subject: {subject}
Topic: {topic}
Primary difficulty: {primary_mistake}

Return ONLY a valid JSON array of 3 objects with:
- prompt: clear question string
- options: list of 4 choices
- answer: exactly one choice from options
- explanation: brief explanation of why this is correct
- mistake_type: {primary_mistake}"""
        raw, status = gemini.generate_text(prompt, max_output_tokens=900)
        if raw:
            try:
                clean = raw.strip()
                fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", clean, re.DOTALL | re.IGNORECASE)
                cand_str = fence_match.group(1) if fence_match else clean

                start_b = cand_str.find("[")
                end_b = cand_str.rfind("]")
                if start_b != -1 and end_b > start_b:
                    cand_str = cand_str[start_b:end_b + 1]

                from agents.gap_finder import _sanitize_json_escapes
                try:
                    items = json.loads(cand_str, strict=False)
                except Exception:
                    items = json.loads(_sanitize_json_escapes(cand_str), strict=False)

                valid = []
                for item in items:
                    if (
                        isinstance(item, dict)
                        and "prompt" in item
                        and "options" in item
                        and "answer" in item
                        and item["answer"] in item["options"]
                        and len(item["options"]) >= 2
                    ):
                        item["id"] = f"prac_{uuid4().hex[:8]}"
                        item.setdefault("explanation", "Check your reasoning and assumptions.")
                        item.setdefault("mistake_type", primary_mistake)
                        valid.append(item)
                if len(valid) == 3:
                    return valid
            except Exception:
                pass

    # Reliable, subject-grounded fallback practice set
    subj_lower = (subject or "").lower()
    clean_topic = topic or "this topic"

    if any(m in subj_lower for m in ["math", "calculus", "algebra", "stat"]):
        return [
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"When starting a problem on {clean_topic}, what should you write down first?",
                "options": [
                    "The given values, known formulas, and what you are solving for",
                    "A random numerical estimate without units",
                    "The final answer directly without intermediate steps",
                    "Only the question number"
                ],
                "answer": "The given values, known formulas, and what you are solving for",
                "explanation": "Clearly identifying given data and the target variable prevents misreading and skipped steps.",
                "mistake_type": "misread"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"After calculating a numerical result in {clean_topic}, how can you quickly verify it?",
                "options": [
                    "Substitute it back into the original condition or check boundary values",
                    "Assume it is right if the number looks neat",
                    "Erase your calculations immediately",
                    "Change the signs to see what happens"
                ],
                "answer": "Substitute it back into the original condition or check boundary values",
                "explanation": "Substitution catches calculation slips and sign errors before you finalize your answer.",
                "mistake_type": "calculation"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"What is the core conceptual foundation required to master {clean_topic}?",
                "options": [
                    "Understanding the underlying definitions and relationships between quantities",
                    "Memorizing isolated calculation steps without the reasons",
                    "Only reading worked examples without attempting unsolved questions",
                    "Skipping questions that require more than one step"
                ],
                "answer": "Understanding the underlying definitions and relationships between quantities",
                "explanation": "True mastery comes from understanding why formulas work, not mechanical memorization.",
                "mistake_type": "conceptual"
            }
        ]
    elif any(s in subj_lower for s in ["science", "physic", "chem", "bio"]):
        return [
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"When explaining a scientific concept in {clean_topic}, what is essential for full marks?",
                "options": [
                    "State the governing law/definition, state the mechanism, and link to observations",
                    "Write as few words as possible",
                    "List disconnected facts without explanation",
                    "Rely only on intuition without scientific terms"
                ],
                "answer": "State the governing law/definition, state the mechanism, and link to observations",
                "explanation": "Scientific explanations require the core principle, mechanism, and context.",
                "mistake_type": "incomplete"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"If an experimental condition changes in {clean_topic}, what should you analyse first?",
                "options": [
                    "Identify which variable is independent, which is dependent, and what is held constant",
                    "Assume none of the variables affect the outcome",
                    "Only measure the final result without checking initial conditions",
                    "Ignore units and control groups"
                ],
                "answer": "Identify which variable is independent, which is dependent, and what is held constant",
                "explanation": "Isolating independent and dependent variables prevents misinterpreting cause and effect.",
                "mistake_type": "conceptual"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"How can you prevent recall slips with key terminology in {clean_topic}?",
                "options": [
                    "Explain the term from memory and relate it to a concrete physical example",
                    "Skim the chapter heading right before an exam",
                    "Avoid writing diagrams or definitions",
                    "Memorize acronyms without knowing what each letter stands for"
                ],
                "answer": "Explain the term from memory and relate it to a concrete physical example",
                "explanation": "Active retrieval paired with concrete examples creates durable memory pathways.",
                "mistake_type": "recall"
            }
        ]
    else:
        return [
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"What is the most effective way to address misinterpretation in {clean_topic}?",
                "options": [
                    "Underline key directives and state the task in your own words before answering",
                    "Start writing immediately without reading the full question",
                    "Ignore formatting and constraints",
                    "Assume the simplest possible interpretation without verification"
                ],
                "answer": "Underline key directives and state the task in your own words before answering",
                "explanation": "Paraphrasing the requirement ensures you address all facets of the prompt.",
                "mistake_type": "misread"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"When reviewing an incomplete answer in {clean_topic}, what should your checklist contain?",
                "options": [
                    "Claim, supporting evidence/logic, connection to the topic, and conclusion",
                    "Only a brief summary sentence",
                    "Unsubstantiated opinions",
                    "A list of bullet points without explanation"
                ],
                "answer": "Claim, supporting evidence/logic, connection to the topic, and conclusion",
                "explanation": "A complete structured answer provides clear reasoning from premise to conclusion.",
                "mistake_type": "incomplete"
            },
            {
                "id": f"p_{uuid4().hex[:8]}",
                "prompt": f"What practice method builds long-term retention for {clean_topic}?",
                "options": [
                    "Spaced self-testing where you explain key ideas without notes",
                    "Re-reading highlighted notes passively",
                    "Studying once for several hours without revision",
                    "Avoiding practice on questions you found difficult earlier"
                ],
                "answer": "Spaced self-testing where you explain key ideas without notes",
                "explanation": "Spaced testing forces active recall, which consolidates long-term retention.",
                "mistake_type": "recall"
            }
        ]
