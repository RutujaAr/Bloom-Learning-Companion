def analyze_test(gemini, results, subject, topic, manual_types=None, notes="", score=None):
    """Analyze diagnostic questions or exam marks into structured mistake recommendations."""
    manual_types = manual_types or []
    counts = {}

    for r in results:
        if not r.get("correct"):
            kind = r.get("question", {}).get("mistake_type", "conceptual")
            counts[kind] = counts.get(kind, 0) + 1

    # Case 1: Manual test session analysis from Marks Analysis page
    if manual_types:
        if gemini and hasattr(gemini, "classify_mistakes"):
            data, _ = gemini.classify_mistakes(subject, topic, notes, manual_types, score if score is not None else 0)
            return data
        # Offline fallback if gemini service object is absent
        return {
            "summary": f"Identified {len(manual_types)} mistake patterns in {topic}.",
            "mistakes": [
                {"type": t.lower().replace(" ", "_"), "label": t, "count": 1, "recommendation": "Review this pattern with targeted practice."}
                for t in manual_types
            ]
        }

    # Case 2: Diagnostic question analysis with recorded errors
    if counts:
        labels = {
            "conceptual": ("Conceptual understanding", "Revisit the core concept and explain it in your own words before attempting more questions."),
            "calculation": ("Calculation accuracy", "Write out intermediate steps and double-check signs, arithmetic, and units."),
            "careless": ("Calculation accuracy", "Write out intermediate steps and double-check signs, arithmetic, and units."),
            "misread": ("Question interpretation", "Highlight given data, constraints, and exactly what is asked before solving."),
            "incomplete": ("Completing the answer", "Use a final check to confirm all working, units, and concluding statements are included."),
            "recall": ("Active recall", "Use spaced flashcards or practice questions to test retrieval from memory.")
        }
        mistakes = []
        for kind, n in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            label, rec = labels.get(kind, (kind.title(), "Practise a similar question and review your reasoning."))
            mistakes.append({"type": kind, "label": label, "count": n, "recommendation": rec})
        total_questions = len(results)
        total_errors = sum(counts.values())
        summary = f"Out of {total_questions} questions, {total_errors} were incorrect. Prioritize the most frequent pattern ({mistakes[0]['label']}) first."
        return {"summary": summary, "mistakes": mistakes}

    # Case 3: Score is provided (e.g. from Marks Analysis) but no mistake types were selected
    if score is not None and score < 100:
        return {
            "summary": f"You scored {score}%. While no specific mistake patterns were marked, reviewing the test solutions for {topic} will highlight where marks were dropped.",
            "mistakes": [{
                "type": "conceptual",
                "label": "Step-by-step review",
                "count": 1,
                "recommendation": f"Work through the questions you missed in {topic} with textbook examples."
            }]
        }

    # Case 4: Perfect score or zero errors
    return {
        "summary": "Full marks recorded! Your understanding is solid. Try a challenge set to check whether your mastery transfers to novel problem formats.",
        "mistakes": []
    }
