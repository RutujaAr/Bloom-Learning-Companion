import json
import re
from core.db import (
    mark_review_done, add_review, get_all_mastery,
    get_review_streak, save_recall_session
)
from core.learning import next_review_days

def generate_recall_prompt(gemini, subject, topic, stage=None, curriculum=None, curriculum_context=None, custom_syllabus=""):
    """
    Generate an active retrieval challenge requiring the student to retrieve
    knowledge from memory without seeing multiple-choice options or answers first.
    Calibrates depth and terminology to the student's educational stage and curriculum.
    """
    topic_str = (topic or "General Topic").strip()
    subj_str = (subject or "General").strip()

    from core.syllabus import build_curriculum_context
    ctx = curriculum_context or build_curriculum_context(stage, curriculum, subj_str, topic_str, custom_syllabus=custom_syllabus)

    if gemini and getattr(gemini, "available", lambda: False)():
        prompt = f"""You are an educational assistant creating an active recall challenge.
{ctx}

Create an active retrieval challenge for a student on the topic '{topic_str}' in '{subj_str}'.
The goal is ACTIVE RECALL (testing knowledge from memory without showing answers).
Align terminology, depth, and rigour with the student's academic profile above.

Return a valid JSON object with:
- "challenge": A specific, high-yield retrieval prompt asking the student to explain the core concept, state key formulas/laws, and describe a real application or mechanism from memory.
- "model_answer": A clear, complete explanation and worked reference answer.
- "key_points": A list of 3-4 key bullet points the student can use to self-assess their recall.

Format response as strictly valid JSON."""

        raw, status = gemini.generate_text(prompt, max_output_tokens=1400)
        if raw:
            try:
                clean = raw.strip()
                fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL | re.IGNORECASE)
                cand_str = fence_match.group(1) if fence_match else clean

                start_brace = cand_str.find("{")
                end_brace = cand_str.rfind("}")
                if start_brace != -1 and end_brace > start_brace:
                    cand_str = cand_str[start_brace:end_brace + 1]

                from agents.gap_finder import _sanitize_json_escapes
                try:
                    data = json.loads(cand_str, strict=False)
                except Exception:
                    data = json.loads(_sanitize_json_escapes(cand_str), strict=False)

                if isinstance(data, dict) and "challenge" in data and "model_answer" in data:
                    return {
                        "challenge": str(data["challenge"]).strip(),
                        "model_answer": str(data["model_answer"]).strip(),
                        "key_points": [str(p) for p in data.get("key_points", []) if p],
                        "source": "AI-generated active retrieval"
                    }
            except Exception:
                pass

    # High-quality offline fallback retrieval challenge
    return {
        "challenge": (
            f"Active Retrieval Challenge for '{topic_str}':\n\n"
            f"1. Explain the fundamental concept and primary definition of {topic_str} in your own words.\n"
            f"2. Write out any essential formulas, governing laws, or step-by-step procedures associated with it.\n"
            f"3. What is a common pitfall, sign error, or misconception that causes marks to be lost in this topic?"
        ),
        "model_answer": (
            f"Comprehensive Concept Summary for '{topic_str}':\n\n"
            f"• Core Principle: Understand how the primary mechanism operates and when to apply it.\n"
            f"• Key Equations / Rules: Verify units, correct sign conventions, and boundary assumptions.\n"
            f"• Self-Check: Ensure you can derive or apply this concept directly to an exam problem without looking at reference material."
        ),
        "key_points": [
            f"Accurately articulated the primary definition/mechanism of {topic_str}",
            "Recalled key formulas, units, or sequential steps correctly",
            "Identified common mistake patterns and edge conditions"
        ],
        "source": "Curated retrieval framework (offline fallback)"
    }

def complete_recall_session(student_id, review_id, subject, topic, prompt, response, self_eval):
    """
    Record an active recall attempt in database and reschedule using spaced repetition logic:
    - Mastered: Marked done and archived (no immediate repeat).
    - Confident / Recalled: Increments spaced repetition streak (1 -> 3 -> 7 -> 14 -> 30 days).
    - Struggled: Resets review to 1 day for prompt reinforcement.
    """
    # 1. Save session record
    session_id = save_recall_session(
        student_id=student_id,
        review_id=review_id,
        subject=subject,
        topic=topic,
        prompt=prompt,
        response=response,
        self_eval=self_eval
    )

    # 2. Mark existing review record as completed
    if review_id:
        mark_review_done(student_id, review_id)

    eval_lower = str(self_eval).lower()

    # 3. Schedule next spaced repetition cycle based on outcome
    if "mastered" in eval_lower:
        return {
            "status": "mastered",
            "days": 0,
            "session_id": session_id,
            "message": f"'{topic}' marked as mastered! Review completed and archived from active queue."
        }
    elif "struggled" in eval_lower:
        # Struggled: reset to 1 day for immediate memory recovery
        add_review(
            student_id,
            subject,
            topic,
            days=1,
            reason="Follow-up revision (reinforce struggling recall)"
        )
        return {
            "status": "scheduled",
            "days": 1,
            "session_id": session_id,
            "message": f"Review recorded. Since recall was challenging, '{topic}' is scheduled for tomorrow to consolidate your memory."
        }
    else:
        # Confident or partial recall: advance spaced repetition streak
        streak = get_review_streak(student_id, subject, topic)
        days = next_review_days(correct=True, streak=streak)
        add_review(
            student_id,
            subject,
            topic,
            days=days,
            reason=f"Spaced revision (cycle {streak + 1})"
        )
        return {
            "status": "scheduled",
            "days": days,
            "session_id": session_id,
            "message": f"Active recall logged! Next spaced revision scheduled in {days} day{'s' if days > 1 else ''}."
        }

def complete_review(student_id, review_id, subject, topic, mastered=False):
    """Legacy helper preserving backward compatibility for automated tests."""
    mark_review_done(student_id, review_id)
    if mastered:
        return {
            "status": "mastered",
            "days": 0,
            "message": f"'{topic}' completed and archived from active reviews."
        }
    streak = get_review_streak(student_id, subject, topic)
    days = next_review_days(correct=True, streak=streak)
    add_review(
        student_id,
        subject,
        topic,
        days=days,
        reason=f"Spaced revision (cycle {streak + 1})"
    )
    return {
        "status": "scheduled",
        "days": days,
        "message": f"Review recorded. Next check scheduled in {days} day{'s' if days > 1 else ''}."
    }

def get_recommendations(student_id):
    """Surface high-priority revision topics based on recorded mistake frequencies."""
    mastery = get_all_mastery(student_id)
    topic_map = {}
    for m in mastery:
        t = m["topic"]
        if t not in topic_map:
            topic_map[t] = {
                "subject": m.get("subject", "General"),
                "topic": t,
                "error_count": m.get("error_count", 0),
                "latest_score": m.get("latest_score", 0)
            }
        else:
            topic_map[t]["error_count"] += m.get("error_count", 0)
            topic_map[t]["latest_score"] = min(topic_map[t]["latest_score"], m.get("latest_score", 0))

    sorted_topics = sorted(topic_map.values(), key=lambda x: x["error_count"], reverse=True)
    return [
        {
            "subject": item["subject"],
            "topic": item["topic"],
            "reason": f"{item['error_count']} recorded mistake(s) · latest score {item['latest_score']}%"
        }
        for item in sorted_topics
    ]
