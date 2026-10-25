"""
Syllabus Alignment Knowledge Base for Bloom.
Contains verified curricula researched from official education boards (e.g. cbseacademic.nic.in)
and structured fallback guidelines for higher education and other boards.
"""

CURRICULA_METADATA = {
    "CBSE": {
        "name": "CBSE (Central Board of Secondary Education)",
        "source": "cbseacademic.nic.in",
        "academic_year": "2024-25",
        "verified": True
    },
    "ICSE": {
        "name": "ICSE / ISC (CISCE)",
        "source": "cisce.org",
        "academic_year": "2024-25",
        "verified": True
    },
    "Cambridge": {
        "name": "Cambridge Assessment (IGCSE / A-Levels)",
        "source": "cambridgeinternational.org",
        "academic_year": "2024-26",
        "verified": True
    },
    "General": {
        "name": "General / University Course Outline",
        "source": "Standard Undergraduate Curriculum",
        "academic_year": "Current",
        "verified": False
    }
}

# Verified syllabus breakdown for CBSE 2024-25
CBSE_SYLLABUS = {
    "Class 10": {
        "Mathematics": {
            "Number Systems": {
                "chapters": ["Real Numbers"],
                "outcomes": ["Fundamental Theorem of Arithmetic", "Proofs of irrationality of √2, √3, √5"],
                "exam_style": "Reasoning and short proof application"
            },
            "Algebra": {
                "chapters": ["Polynomials", "Pair of Linear Equations in Two Variables", "Quadratic Equations", "Arithmetic Progressions"],
                "outcomes": ["Zeros of polynomials", "Graphical and algebraic solution methods (substitution, elimination)", "Discriminant and nature of roots", "nth term and sum of first n terms of AP"],
                "exam_style": "Multi-step problem solving, word problems, and formula derivation"
            },
            "Coordinate Geometry": {
                "chapters": ["Coordinate Geometry"],
                "outcomes": ["Distance formula", "Section formula (internal division)"],
                "exam_style": "Geometric calculation and algebraic substitution"
            },
            "Geometry": {
                "chapters": ["Triangles", "Circles"],
                "outcomes": ["Basic Proportionality Theorem (Thales)", "Tangent to a circle perpendicular to radius", "Lengths of tangents from external point"],
                "exam_style": "Formal geometric deduction and multi-step rider problems"
            },
            "Trigonometry": {
                "chapters": ["Introduction to Trigonometry", "Trigonometric Identities", "Heights and Distances"],
                "outcomes": ["Trigonometric ratios of acute angles", "Values at 0°, 30°, 45°, 60°, 90°", "Proof and application of sin²θ + cos²θ = 1", "Angle of elevation and depression calculations"],
                "exam_style": "Identity transformation, multi-step calculation, and practical measurement"
            },
            "Mensuration": {
                "chapters": ["Areas Related to Circles", "Surface Areas and Volumes"],
                "outcomes": ["Area of sectors and segments", "Surface area and volume of combinations of solids (cubes, spheres, cylinders, cones)"],
                "exam_style": "Calculation accuracy with units and composite solid decomposition"
            },
            "Statistics & Probability": {
                "chapters": ["Statistics", "Probability"],
                "outcomes": ["Mean, median and mode of grouped data", "Classical definition of simple probability"],
                "exam_style": "Tabular computation and event probability reasoning"
            }
        },
        "Science": {
            "Chemical Substances - Nature & Behaviour": {
                "chapters": ["Chemical Reactions and Equations", "Acids, Bases and Salts", "Metals and Non-metals", "Carbon and its Compounds"],
                "outcomes": ["Balancing equations", "Types of reactions", "pH scale applications", "Electrolytic refining", "Covalent bonding and homologous series"],
                "exam_style": "Chemical equation balancing, property identification, and reaction observation interpretation"
            },
            "World of Living": {
                "chapters": ["Life Processes", "Control and Coordination", "How do Organisms Reproduce?", "Heredity"],
                "outcomes": ["Nutrition, respiration, transport, and excretion in plants/animals", "Tropic movements and plant hormones", "Sexual vs asexual reproduction", "Mendelian inheritance principles"],
                "exam_style": "Process mechanisms, comparative analysis, and genetic cross interpretations"
            },
            "Natural Phenomena": {
                "chapters": ["Light - Reflection and Refraction", "The Human Eye and Colourful World"],
                "outcomes": ["Laws of reflection and refraction", "Mirror and lens formula with sign conventions", "Defects of vision and correction", "Atmospheric refraction and dispersion"],
                "exam_style": "Ray diagram deductions, sign-convention numericals, and optical phenomena explanations"
            },
            "Effects of Current": {
                "chapters": ["Electricity", "Magnetic Effects of Electric Current"],
                "outcomes": ["Ohm's law and V-I characteristics", "Series and parallel resistance combinations", "Joule's law of heating", "Magnetic field around a solenoid", "Fleming's left-hand rule"],
                "exam_style": "Circuit calculations, power ratings, and magnetic field direction rules"
            }
        }
    },
    "Class 12": {
        "Mathematics": {
            "Calculus": {
                "chapters": ["Continuity and Differentiability", "Applications of Derivatives", "Integrals", "Applications of the Integrals", "Differential Equations"],
                "outcomes": ["Chain rule, logarithmic differentiation", "Rate of change, maxima and minima", "Integration by parts and partial fractions", "Area under curves", "Homogeneous and linear differential equations"],
                "exam_style": "Rigorous multi-step calculus, optimization modeling, and integral evaluations"
            },
            "Vectors & 3D Geometry": {
                "chapters": ["Vectors", "Three-Dimensional Geometry"],
                "outcomes": ["Scalar and vector products", "Direction cosines and ratios", "Equation of lines in space, shortest distance between skew lines"],
                "exam_style": "Vector algebra, spatial coordinate reasoning, and geometric proof"
            },
            "Probability": {
                "chapters": ["Probability"],
                "outcomes": ["Conditional probability", "Multiplication theorem", "Bayes' theorem"],
                "exam_style": "Multi-stage stochastic problem solving and prior/posterior probability formulation"
            }
        },
        "Physics": {
            "Electrostatics & Current": {
                "chapters": ["Electric Charges and Fields", "Electrostatic Potential and Capacitance", "Current Electricity"],
                "outcomes": ["Gauss's law applications", "Capacitor combinations and energy storage", "Kirchhoff's rules and Wheatstone bridge"],
                "exam_style": "Field integrations, circuit network calculations, and potential derivations"
            },
            "Electromagnetism & Optics": {
                "chapters": ["Moving Charges and Magnetism", "Electromagnetic Induction", "Alternating Current", "Ray Optics", "Wave Optics"],
                "outcomes": ["Biot-Savart and Ampere's laws", "Faraday's law and Lenz's law", "LCR series resonance", "Lens maker's formula", "Huygens' principle and Young's double slit interference"],
                "exam_style": "Derivations, circuit phasors, optical geometry, and wave interference conditions"
            }
        },
        "Chemistry": {
            "Physical Chemistry": {
                "chapters": ["Solutions", "Electrochemistry", "Chemical Kinetics"],
                "outcomes": ["Raoult's law and colligative properties", "Nernst equation and cell EMF", "Rate law, order of reaction, and Arrhenius activation energy"],
                "exam_style": "Numerical calculations with units, logarithmic plots, and electrochemical stoichiometry"
            },
            "Organic Chemistry": {
                "chapters": ["Haloalkanes and Haloarenes", "Alcohols, Phenols and Ethers", "Aldehydes, Ketones and Carboxylic Acids", "Amines"],
                "outcomes": ["SN1 and SN2 mechanisms", "Name reactions (Aldol, Cannizzaro, Sandmeyer)", "Electrophilic aromatic substitutions", "Distinction tests"],
                "exam_style": "Mechanism pathways, multi-step chemical synthesis, and qualitative identification"
            }
        }
    }
}

def get_supported_curricula(stage=None):
    """
    Return appropriate curricula choices based on the learner's education stage.
    Ensures College/University students are not defaulted to school boards like CBSE.
    """
    if stage == "College":
        return [
            "University / Degree Curriculum",
            "College Course Outline",
            "Autonomous / State University Syllabus",
            "Technical / Professional Programme",
            "Custom Syllabus (Learner-Supplied)"
        ]
    elif stage == "Research / PhD":
        return [
            "Postgraduate / Research Programme",
            "Specialized Academic Literature",
            "Custom Research Focus"
        ]
    elif stage == "Class 12":
        return [
            "CBSE (Reference Syllabus)",
            "ISC (CISCE Curriculum)",
            "State Board Syllabus",
            "Cambridge (A-Levels)",
            "Custom Syllabus (Learner-Supplied)"
        ]
    elif stage == "Class 10":
        return [
            "CBSE (Reference Syllabus)",
            "ICSE (CISCE Curriculum)",
            "State Board Syllabus",
            "Cambridge (IGCSE)",
            "Custom Syllabus (Learner-Supplied)"
        ]
    # Default list when stage is unspecified (preserves backwards-compatibility with legacy references)
    return [
        "University / Degree Curriculum",
        "College / University Outline",
        "CBSE (Reference Syllabus)",
        "CBSE (Verified 2024-25)",
        "ICSE / ISC (CISCE 2024-25)",
        "State Board / Standard Curriculum",
        "Cambridge (IGCSE / A-Levels)",
        "Custom Syllabus (Learner-Supplied)",
        "Other / General"
    ]

import functools

@functools.lru_cache(maxsize=256)
def get_syllabus_context(stage, curriculum_name, subject, topic):
    """
    Match the topic against verified syllabus records or provide an honest disclaimer.
    Cached via lru_cache to prevent redundant lookups for repeated topics.
    Returns metadata dict for grounding question generation.
    """
    curriculum_key = "CBSE" if "CBSE" in str(curriculum_name) else ("General")
    clean_topic = (topic or "").strip().lower()
    clean_subj = (subject or "").strip().title()

    stage_data = CBSE_SYLLABUS.get(stage, {})
    subj_data = stage_data.get(clean_subj, {})

    # Check for chapter or unit match
    matched_unit = None
    matched_details = None

    for unit_name, details in subj_data.items():
        if clean_topic in unit_name.lower():
            matched_unit = unit_name
            matched_details = details
            break
        for ch in details.get("chapters", []):
            if clean_topic in ch.lower() or ch.lower() in clean_topic:
                matched_unit = unit_name
                matched_details = details
                break

    if curriculum_key == "CBSE" and matched_details:
        meta = CURRICULA_METADATA["CBSE"]
        return {
            "verified": True,
            "curriculum": f"CBSE {stage} (Reference Curriculum)",
            "source": f"Official Portal {meta['source']}",
            "unit": matched_unit,
            "chapters": ", ".join(matched_details.get("chapters", [])),
            "outcomes": "; ".join(matched_details.get("outcomes", [])),
            "exam_style": matched_details.get("exam_style", "Conceptual application and multi-step calculation"),
            "disclaimer": f"Aligned with official CBSE {stage} reference syllabus published on {meta['source']}."
        }

    # If unverified, higher education, or outside curated CBSE index
    default_curr = "University / Degree Curriculum" if stage == "College" else "Standard Educational Framework"
    active_curr = curriculum_name or default_curr
    return {
        "verified": False,
        "curriculum": active_curr,
        "source": "Learner-selected / Standard Academic Outline",
        "unit": topic,
        "chapters": topic,
        "outcomes": f"Core principles, problem-solving, and applications of {topic}",
        "exam_style": "Exam-style application, conceptual reasoning, and worked problem-solving",
        "disclaimer": f"No verified board syllabus cache found for this specific subject/topic. Questions and explanations follow core academic principles for {stage or 'Learner'}."
    }


def build_curriculum_context(stage, curriculum, subject="", topic="", custom_syllabus=""):
    """
    Single reliable curriculum and education stage context builder for AI generation prompts
    across Bloom (diagnostic gaps, textbook helper, recall & revision, personal study guide).
    Genuinely personalizes terminology, analytical depth, problem-solving methods, and syllabus scope.
    """
    s_stage = (stage or "College").strip()
    s_curr = (curriculum or ("University / Degree Curriculum" if s_stage == "College" else "Standard Educational Framework")).strip()
    c_syl = (custom_syllabus or "").strip()

    # Stage-specific pedagogical directives
    if s_stage == "Class 10":
        pedagogy = (
            "PEDAGOGICAL LEVEL & TERMINOLOGY DIRECTIVES (Class 10 / Secondary Level - Ages 15-16):\n"
            "- Terminology: Use clear, age-appropriate, foundational academic terms. Avoid advanced calculus, post-secondary abstraction, or graduate research jargon.\n"
            "- Explanations: Concrete everyday analogies, clear intuitive models, and step-by-step arithmetic/algebraic steps.\n"
            "- Scope & Style: Adhere strictly to secondary school board curriculum standards and foundational definitions."
        )
    elif s_stage == "Class 12":
        pedagogy = (
            "PEDAGOGICAL LEVEL & TERMINOLOGY DIRECTIVES (Class 12 / Senior Secondary - Ages 17-18):\n"
            "- Terminology: Use formal senior-secondary terminology, standard physical/mathematical derivations, chemical reaction mechanisms, and symbolic proofs.\n"
            "- Explanations: Deep analytical reasoning, rigorous multi-step problem solving, and standard pre-university exam rigor.\n"
            "- Scope & Style: Target senior-secondary / entrance exam benchmarks without oversimplification."
        )
    elif s_stage == "Research / PhD":
        pedagogy = (
            "PEDAGOGICAL LEVEL & TERMINOLOGY DIRECTIVES (Research / PhD Level - Doctoral Study):\n"
            "- Terminology: Specialist domain vocabulary, state-of-the-art methodology, theoretical bounds, and formal notation.\n"
            "- Explanations: Advanced critical evaluation, comparative paradigms, open problems, and algorithmic/theoretical trade-offs.\n"
            "- Scope & Style: Maintain doctoral rigour without hallucinating or inventing fabricated research citations or DOIs."
        )
    else:  # College / Undergraduate
        pedagogy = (
            "PEDAGOGICAL LEVEL & TERMINOLOGY DIRECTIVES (College / Undergraduate Level):\n"
            "- Terminology: Formal university academic terminology, algorithmic complexity, architectural design patterns, and formal proofs.\n"
            "- Explanations: Undergraduate depth, system-level trade-offs, formal implementations, and worked engineering/scientific problem solving.\n"
            "- Scope & Style: University degree syllabus standards bridging fundamentals to practical application."
        )

    syl = get_syllabus_context(s_stage, s_curr, subject or "General", topic or "Core Concepts")
    custom_clause = f"\nUser-Supplied Course/Syllabus Outline: {c_syl}" if c_syl else ""

    # Defensive check: if contradictory stage & board (e.g. College + CBSE), explicitly enforce stage
    conflict_note = ""
    if s_stage in ("College", "Research / PhD") and "CBSE" in s_curr:
        conflict_note = f"\nNote: Learner stage is {s_stage}; calibrate terminology and depth to {s_stage} level despite school board framework reference."

    if syl.get("verified"):
        return (
            f"ACADEMIC PROFILE & CURRICULUM CONTEXT:\n"
            f"Education Stage: {s_stage}\n"
            f"Curriculum Framework: {syl['curriculum']}\n"
            f"Syllabus Source: {syl['source']}\n"
            f"Syllabus Unit/Chapters: {syl.get('chapters') or syl.get('unit')}\n"
            f"Target Outcomes: {syl.get('outcomes')}\n"
            f"Expected Rigor: {syl.get('exam_style')}{custom_clause}{conflict_note}\n\n"
            f"{pedagogy}"
        )
    else:
        topic_clause = f" on {topic}" if topic else ""
        return (
            f"ACADEMIC PROFILE & CURRICULUM CONTEXT:\n"
            f"Education Stage: {s_stage}\n"
            f"Curriculum Framework: {syl['curriculum']}\n"
            f"Syllabus Grounding: {syl.get('source', 'Learner-selected outline')}\n"
            f"Subject & Topic: {subject or 'General'}{topic_clause}{custom_clause}{conflict_note}\n\n"
            f"{pedagogy}"
        )
