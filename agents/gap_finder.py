import time
import json
import re
from uuid import uuid4
from core.syllabus import get_syllabus_context

BANKS = {
    "math": [
        {
            "prompt": "A student solves the quadratic equation 2x² - 8x + 6 = 0 using the quadratic formula. What is the value of the discriminant (b² - 4ac)?",
            "options": ["16", "-16", "112", "4"],
            "answer": "16",
            "explanation": "Here a=2, b=-8, c=6. Discriminant = (-8)² - 4(2)(6) = 64 - 48 = 16. Since 16 > 0, there are two distinct real roots.",
            "hint": "Remember to square the entire coefficient (-8), which yields +64.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "A car accelerates uniformly from rest to 20 m/s over a distance of 50 meters. What is the acceleration of the car?",
            "options": ["4 m/s²", "2 m/s²", "8 m/s²", "0.4 m/s²"],
            "answer": "4 m/s²",
            "explanation": "Using v² = u² + 2as: 20² = 0² + 2(a)(50) => 400 = 100a => a = 4 m/s².",
            "hint": "Identify the kinematic equation connecting initial velocity, final velocity, distance, and acceleration without time.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "If the 7th term of an Arithmetic Progression is 20 and the common difference is 3, what is the first term (a)?",
            "options": ["2", "5", "8", "-1"],
            "answer": "2",
            "explanation": "Formula: a_n = a + (n - 1)d. For n=7: 20 = a + (7 - 1)(3) => 20 = a + 18 => a = 2.",
            "hint": "The 7th term adds 6 common differences to the first term.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "In a right-angled triangle, if tan(θ) = 3/4, what is the value of cos(θ)?",
            "options": ["4/5", "3/5", "5/4", "5/3"],
            "answer": "4/5",
            "explanation": "tan(θ) = opposite / adjacent = 3/4. By Pythagorean theorem, hypotenuse = √(3² + 4²) = 5. Therefore, cos(θ) = adjacent / hypotenuse = 4/5.",
            "hint": "Find the hypotenuse using the 3-4-5 Pythagorean triple first.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "A cylindrical tank has radius 7 m and height 10 m. Using π = 22/7, what is the total curved surface area (CSA)?",
            "options": ["440 m²", "220 m²", "1540 m²", "748 m²"],
            "answer": "440 m²",
            "explanation": "Curved surface area of a cylinder = 2πrh = 2 × (22/7) × 7 × 10 = 440 m².",
            "hint": "Curved surface area does not include the top and bottom circular bases.",
            "mistake_type": "misread"
        },
        {
            "prompt": "If P(A) = 0.35, what is the probability of the complement event, P(not A)?",
            "options": ["0.65", "0.35", "-0.35", "1.35"],
            "answer": "0.65",
            "explanation": "The sum of probabilities of complementary events equals 1: P(not A) = 1 - 0.35 = 0.65.",
            "hint": "Total probability of all mutually exclusive and exhaustive outcomes is always 1.",
            "mistake_type": "recall"
        },
        {
            "prompt": "A line passes through (2, 3) and (6, 11). What is the slope (gradient) of this line?",
            "options": ["2", "1/2", "4", "8"],
            "answer": "2",
            "explanation": "Slope m = (y₂ - y₁) / (x₂ - x₁) = (11 - 3) / (6 - 2) = 8 / 4 = 2.",
            "hint": "Slope is vertical rise over horizontal run: Δy / Δx.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "A student gets 3x + 5 = 20. What should they do first to isolate x systematically?",
            "options": ["Subtract 5 from both sides", "Divide only 3 by 5", "Add 20 to both sides", "Square both sides"],
            "answer": "Subtract 5 from both sides",
            "explanation": "Undo the constant term +5 first by subtracting 5 from both sides to yield 3x = 15.",
            "hint": "Reverse operations starting with addition/subtraction before multiplication/division.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "If 2x - 3y = 7 and y = 1, what is the value of x?",
            "options": ["5", "2", "4", "10"],
            "answer": "5",
            "explanation": "Substitute y = 1 into the equation: 2x - 3(1) = 7 => 2x = 10 => x = 5.",
            "hint": "Substitute the given value of y directly into the linear equation.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "What is the median of the data set: 3, 7, 2, 9, 5?",
            "options": ["5", "7", "5.2", "2"],
            "answer": "5",
            "explanation": "First arrange in ascending order: 2, 3, 5, 7, 9. The middle (3rd) value is 5.",
            "hint": "Always sort numbers in ascending order before locating the median.",
            "mistake_type": "misread"
        }
    ],
    "science": [
        {
            "prompt": "When aqueous barium chloride reacts with sodium sulphate, what white precipitate is formed?",
            "options": ["Barium sulphate (BaSO₄)", "Sodium chloride (NaCl)", "Barium sulphite (BaSO₃)", "Sodium sulphide (Na₂S)"],
            "answer": "Barium sulphate (BaSO₄)",
            "explanation": "This is a double displacement precipitation reaction: BaCl₂(aq) + Na₂SO₄(aq) -> BaSO₄(s) + 2NaCl(aq).",
            "hint": "Look at which combination of swapped ions produces an insoluble salt in water.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "An electric circuit has a 12 V battery connected across three 2 Ω resistors in series. What is the total current leaving the battery?",
            "options": ["2 A", "6 A", "18 A", "0.5 A"],
            "answer": "2 A",
            "explanation": "Total resistance R_eq = 2 + 2 + 2 = 6 Ω. Current I = V / R = 12 / 6 = 2 A.",
            "hint": "In series, individual resistances add up directly.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "An object is placed 20 cm in front of a concave mirror of focal length 10 cm. Where is the real image formed?",
            "options": ["At 20 cm in front of the mirror (at Center of Curvature)", "At 10 cm behind the mirror", "At infinity", "At 5 cm in front of the mirror"],
            "answer": "At 20 cm in front of the mirror (at Center of Curvature)",
            "explanation": "The center of curvature C is at 2f = 20 cm. When an object is at C, its real, inverted image is formed exactly at C (20 cm).",
            "hint": "Notice that object distance u = 20 cm equals 2 × focal length f = 10 cm.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "During cellular respiration in human muscle cells under anaerobic conditions (lack of oxygen), what end product accumulates?",
            "options": ["Lactic acid and energy", "Ethanol and carbon dioxide", "Water and carbon dioxide", "Acetic acid"],
            "answer": "Lactic acid and energy",
            "explanation": "In human muscle tissue during intense activity, pyruvate is converted into lactic acid, causing muscle cramps.",
            "hint": "Ethanol fermentation occurs in yeast, whereas muscles produce an acid associated with fatigue.",
            "mistake_type": "recall"
        },
        {
            "prompt": "Which of the following represents a balanced chemical equation for the combustion of methane?",
            "options": ["CH₄ + 2O₂ -> CO₂ + 2H₂O", "CH₄ + O₂ -> CO₂ + H₂O", "CH₄ + 3O₂ -> CO₂ + 2H₂O", "2CH₄ + 3O₂ -> 2CO₂ + 4H₂O"],
            "answer": "CH₄ + 2O₂ -> CO₂ + 2H₂O",
            "explanation": "Reactants: 1 C, 4 H, 4 O. Products: 1 C, 4 H (2×2), 4 O (2 + 2×1). Both mass and atoms are conserved.",
            "hint": "Check that the number of oxygen atoms matches on both sides of the arrow.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "What happens to the resistance of a cylindrical metallic wire if its length is doubled and its cross-sectional area is halved?",
            "options": ["Increases by 4 times", "Doubles", "Remains unchanged", "Decreases to one-fourth"],
            "answer": "Increases by 4 times",
            "explanation": "Resistance R = ρ·(L / A). If L becomes 2L and A becomes A/2, R' = ρ·(2L / (A/2)) = 4 · (ρL/A) = 4R.",
            "hint": "Resistance is directly proportional to length and inversely proportional to area.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "A cross between a homozygous tall pea plant (TT) and a homozygous dwarf plant (tt) produces F1 offspring. What is the phenotypic ratio in the F2 generation?",
            "options": ["3 Tall : 1 Dwarf", "1 Tall : 2 Medium : 1 Dwarf", "All Tall", "1 Tall : 1 Dwarf"],
            "answer": "3 Tall : 1 Dwarf",
            "explanation": "F1 genotype is Tt (all tall). Crossing Tt × Tt gives genotypes 1 TT, 2 Tt, 1 tt, yielding a 3:1 phenotypic ratio (3 tall : 1 dwarf).",
            "hint": "Remember the classic Mendelian monohybrid cross phenotypic ratio.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Why does the sky appear blue on a clear sunny day?",
            "options": ["Shorter blue wavelengths are scattered more by fine air molecules (Rayleigh scattering)", "The ocean reflects blue light into the atmosphere", "Dust particles absorb all red wavelengths", "Water vapor specifically emits blue photons"],
            "answer": "Shorter blue wavelengths are scattered more by fine air molecules (Rayleigh scattering)",
            "explanation": "Rayleigh scattering is inversely proportional to λ⁴. Shorter blue wavelengths scatter much more than longer red wavelengths.",
            "hint": "Scattering intensity is highest for shorter wavelengths of visible light.",
            "mistake_type": "recall"
        }
    ],
    "general": [
        {
            "prompt": "A researcher hypothesizes that studying in 25-minute intervals with 5-minute breaks improves memory retention compared to 2-hour uninterrupted cramming. What is the independent variable?",
            "options": ["The study schedule interval structure", "The memory retention test score", "The age of the participants", "The difficulty of the study material"],
            "answer": "The study schedule interval structure",
            "explanation": "The independent variable is the condition intentionally varied or manipulated by the experimenter.",
            "hint": "Which variable is manipulated as the cause rather than measured as the outcome?",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Which study technique provides the strongest empirical evidence for long-term concept retention and transfer?",
            "options": ["Spaced active retrieval practice with self-testing", "Passive highlighting and re-reading textbook chapters", "Cramming review sheets the night before an exam", "Transcribing lecture recordings word-for-word"],
            "answer": "Spaced active retrieval practice with self-testing",
            "explanation": "Cognitive psychology demonstrates that effortful retrieval practice strengthens neural pathways and memory consolidation.",
            "hint": "Actively recalling information from memory produces stronger learning than passive exposure.",
            "mistake_type": "recall"
        },
        {
            "prompt": "When an exam prompt instructs a student to 'critically evaluate' a theoretical model, what does the examiner expect?",
            "options": ["Discuss both strengths and limitations, supported by evidence and practical implications", "Only summarize the definition of the model", "State a personal opinion without reference to evidence", "List biographical details of the model's creator"],
            "answer": "Discuss both strengths and limitations, supported by evidence and practical implications",
            "explanation": "'Critically evaluate' requires a balanced analysis of validity, supporting evidence, shortcomings, and practical relevance.",
            "hint": "Look for the answer that requires balanced analysis rather than one-sided summary.",
            "mistake_type": "misread"
        },
        {
            "prompt": "A chart shows sales increased by 20% in Year 1 and then decreased by 20% in Year 2. Compared to the starting value, the final value is:",
            "options": ["4% lower than starting value", "Equal to starting value", "4% higher than starting value", "2% lower than starting value"],
            "answer": "4% lower than starting value",
            "explanation": "Starting at 100: 100 × 1.20 = 120. Then 120 × 0.80 = 96. The net change is -4% (a 4% decrease).",
            "hint": "The second percentage change applies to the new, higher intermediate value, not the original 100.",
            "mistake_type": "calculation"
        }
    ],
    "machine_learning": [
        {
            "prompt": "In supervised learning, what primary problem is caused when a high-capacity model achieves near-zero training loss but exhibits very high validation error?",
            "options": ["Overfitting (High Variance)", "Underfitting (High Bias)", "Data leakage", "Vanishing gradient"],
            "answer": "Overfitting (High Variance)",
            "explanation": "Overfitting occurs when a model memorizes noise and specific patterns in the training data rather than generalizing, resulting in high variance between training and validation performance.",
            "hint": "Consider the bias-variance tradeoff when model capacity is too high relative to data size.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "A binary classification model detects fraud. Out of 100 actual fraud cases, the model flags 80 correctly and misses 20. What is the Recall (Sensitivity) of the model?",
            "options": ["80%", "20%", "75%", "90%"],
            "answer": "80%",
            "explanation": "Recall = True Positives / (True Positives + False Negatives) = 80 / (80 + 20) = 80 / 100 = 80%.",
            "hint": "Recall measures the proportion of actual positive cases that were correctly captured.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "During gradient descent optimization, what typically happens to training if the learning rate (alpha) is set excessively high?",
            "options": ["Loss diverges or oscillates without converging", "Loss gets permanently stuck at initial value", "Training converges in exactly one step", "Model automatically underfits due to regularization"],
            "answer": "Loss diverges or oscillates without converging",
            "explanation": "An excessively large learning rate causes gradient descent to overshoot the loss minimum, causing oscillating updates or numerical divergence to infinity.",
            "hint": "Think about what happens to parameter updates when steps across the loss landscape are too large.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Which evaluation metric is mathematically defined as the harmonic mean of Precision and Recall?",
            "options": ["F1-Score", "ROC-AUC", "Mean Squared Error", "Cross-Entropy Loss"],
            "answer": "F1-Score",
            "explanation": "F1-Score = 2 * (Precision * Recall) / (Precision + Recall), providing a balanced metric especially when class distributions are imbalanced.",
            "hint": "The harmonic mean penalizes extreme values between two rates more heavily than an arithmetic mean.",
            "mistake_type": "recall"
        }
    ],
    "computer_vision": [
        {
            "prompt": "A convolutional layer receives an input feature map of dimensions 32×32 with 3 channels. It applies a 5×5 convolution filter with stride 1 and 'valid' padding (no zero-padding). What is the spatial height and width of the resulting feature map?",
            "options": ["28×28", "32×32", "27×27", "30×30"],
            "answer": "28×28",
            "explanation": "Output spatial dimension = (W - K + 2P)/S + 1 = (32 - 5 + 0)/1 + 1 = 28×28.",
            "hint": "Use the standard convolutional output dimension formula: (W - K + 2P)/S + 1.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "In a convolutional neural network for image classification, what is the primary spatial and computational purpose of applying a 2×2 Max Pooling layer with stride 2?",
            "options": [
                "Reduces spatial dimensions by 75% to achieve translation invariance and decrease computational load",
                "Increases the number of color channels from 1 to 3",
                "Introduces non-linear learnable weight matrices to sharpen edges",
                "Normalizes pixel intensities to have zero mean and unit variance"
            ],
            "answer": "Reduces spatial dimensions by 75% to achieve translation invariance and decrease computational load",
            "explanation": "A 2×2 max pooling operation downsamples width and height by half, reducing total spatial area by 75% while providing translation invariance and reducing downstream parameter counts.",
            "hint": "Think about the effect of halving both height and width on the total number of activations.",
            "mistake_type": "conceptual"
        },
        {
            "prompt": "Which 3×3 convolution kernel is standardly used as a horizontal Sobel operator (Gx) to compute image intensity gradients in the horizontal direction?",
            "options": [
                "[[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]",
                "[[-1, -2, -1], [0, 0, 0], [1, 2, 1]]",
                "[[0, -1, 0], [-1, 4, -1], [0, -1, 0]]",
                "[[1/9, 1/9, 1/9], [1/9, 1/9, 1/9], [1/9, 1/9, 1/9]]"
            ],
            "answer": "[[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]",
            "explanation": "The horizontal Sobel filter has negative weights on the left column, zeros in the center, and positive weights on the right column to compute horizontal finite difference gradients.",
            "hint": "Horizontal gradients detect vertical edges by taking the difference between right and left pixel columns.",
            "mistake_type": "recall"
        },
        {
            "prompt": "In visual object detection, a predicted bounding box has an area of 50 pixels, the ground truth box has an area of 50 pixels, and their overlapping intersection has an area of 20 pixels. What is the Intersection over Union (IoU)?",
            "options": ["0.25", "0.40", "0.20", "0.50"],
            "answer": "0.25",
            "explanation": "Union = Area(A) + Area(B) - Intersection = 50 + 50 - 20 = 80 pixels. IoU = Intersection / Union = 20 / 80 = 0.25.",
            "hint": "Remember that Union equals Area_1 + Area_2 minus the overlapping intersection.",
            "mistake_type": "calculation"
        },
        {
            "prompt": "An image processing pipeline requires the output feature map of a 2D convolution to have the exact same spatial height and width as the input ('same' padding) using a 7×7 filter and stride 1. How many pixels of zero-padding (P) must be added to each border of the image?",
            "options": ["3 pixels", "7 pixels", "6 pixels", "1 pixel"],
            "answer": "3 pixels",
            "explanation": "To preserve spatial dimensions with stride 1: P = (K - 1) / 2 = (7 - 1) / 2 = 3 pixels on each side.",
            "hint": "For odd kernel size K with stride 1, padding on each side is (K - 1) / 2.",
            "mistake_type": "conceptual"
        }
    ]
}

# Alias cs_ai to machine_learning for backward compatibility
BANKS["cs_ai"] = BANKS["machine_learning"]

LAST_DIAGNOSTIC_METRICS = {
    "syllabus_lookup_s": 0.0,
    "ai_generation_s": 0.0,
    "fallback_lookup_s": 0.0,
    "total_elapsed_s": 0.0,
    "source_used": "none",
    "question_count": 0,
    "api_attempts": [],
    "model": "gemini-3.8-flash",
    "timed_out": False
}

def get_last_diagnostic_metrics():
    """Return a copy of diagnostic latency and attempt metrics from the most recent run."""
    return dict(LAST_DIAGNOSTIC_METRICS)

def normalize_question_prompt(text):
    """Normalize question prompt for strict case- and punctuation-insensitive anti-repetition comparison."""
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _get_fallback_bank(subject, topic="", level="Standard"):
    """
    Select fallback questions only when their topic and domain are genuinely relevant to the request.
    Never return generic Machine Learning questions as a fallback for Computer Vision or unrelated topics.
    """
    s = (subject or "").lower().strip()
    t = (topic or "").lower().strip()

    # 1. Computer Vision specific keywords (must match before any CS / ML checks)
    cv_keywords = [
        "computer vision", "vision", "cv", "object detection", "image classification",
        "convolutional", "cnn", "image processing", "yolo", "segmentation",
        "bounding box", "sobel", "filter kernel", "max pooling", "feature map", "iou"
    ]
    if any(k in t for k in cv_keywords) or (s == "computer science" and any(k in t for k in ["vision", "image", "cv", "cnn"])):
        return BANKS.get("computer_vision", [])

    # 2. Machine Learning specific keywords (do NOT match bare "computer" or "science")
    ml_keywords = [
        "machine learning", "supervised learning", "unsupervised learning",
        "gradient descent", "overfitting", "underfitting", "bias variance",
        "classification", "regression", "precision", "recall", "f1-score"
    ]
    if any(k in t for k in ml_keywords) or (s in ["computer science", "other"] and t in ["machine learning", "ml", "ai", "artificial intelligence", "deep learning"]):
        return BANKS.get("machine_learning", [])

    # 3. Mathematics specific keywords
    math_keywords = [
        "math", "calculus", "algebra", "stat", "trig", "geom", "number", "quadratic",
        "arithmetic", "probability", "linear equation", "discriminant", "slope", "median",
        "pythagorean", "cylinder", "surface area", "kinematic"
    ]
    if any(k in t for k in math_keywords) or (s in ["mathematics", "math"] and (not t or any(k in t for k in math_keywords))):
        return BANKS.get("math", [])

    # 4. Science / Physics / Chemistry / Biology specific keywords
    science_keywords = [
        "physics", "chemistry", "biology", "sci", "phys", "chem", "bio", "cell",
        "electric", "optics", "current", "reaction", "acid", "plant", "organism",
        "circuit", "mirror", "resistor", "precipitation", "genetics", "rayleigh",
        "photosynthesis", "respiration", "mendelian", "barium"
    ]
    if any(k in t for k in science_keywords) or (s in ["science", "physics", "chemistry", "biology"] and (not t or any(k in t for k in science_keywords))):
        return BANKS.get("science", [])

    # 5. Study skills / exam technique (only if explicitly requested)
    study_keywords = ["study technique", "retention", "spaced practice", "active recall", "critical thinking", "exam technique"]
    if any(k in t for k in study_keywords):
        return BANKS.get("general", [])

    # 6. Any other topic: No relevant fallback exists
    return []

def _validate_question_structure(item):
    """Validate that question dictionary satisfies strict multi-choice schema and answer key consistency."""
    if not isinstance(item, dict):
        return False, "Not a dictionary"
    for key in ["prompt", "options", "answer", "explanation"]:
        if key not in item or not str(item[key]).strip():
            return False, f"Missing or empty '{key}'"
    if not isinstance(item["options"], list) or len(item["options"]) < 3:
        return False, "Options must be a list with at least 3 choices"

    cleaned_options = [str(opt).strip() for opt in item["options"]]
    if len(set(cleaned_options)) != len(cleaned_options):
        return False, "Duplicate choices in options list"

    clean_ans = str(item["answer"]).strip()

    # 1. Exact match
    if clean_ans in cleaned_options:
        item["options"] = cleaned_options
        return True, "Valid"

    # 2. Case-insensitive match
    matched = next((opt for opt in cleaned_options if opt.lower() == clean_ans.lower()), None)
    if matched:
        item["answer"] = matched
        item["options"] = cleaned_options
        return True, "Valid"

    # 3. Single letter answer: 'A' -> option 0, 'B' -> option 1, etc.
    if len(clean_ans) == 1 and clean_ans.upper() in "ABCDEF":
        idx = ord(clean_ans.upper()) - ord("A")
        if 0 <= idx < len(cleaned_options):
            item["answer"] = cleaned_options[idx]
            item["options"] = cleaned_options
            return True, "Valid"

    # 4. Handle letter prefix mismatches (e.g. 'C) Option text' vs 'Option text')
    clean_ans_stripped = re.sub(r"^[A-Fa-f0-9][\).\s]+", "", clean_ans).strip()
    for opt in cleaned_options:
        opt_stripped = re.sub(r"^[A-Fa-f0-9][\).\s]+", "", opt).strip()
        if clean_ans_stripped and (opt_stripped.lower() == clean_ans_stripped.lower() or opt.lower() == clean_ans_stripped.lower()):
            item["answer"] = opt
            item["options"] = cleaned_options
            return True, "Valid"
        if len(clean_ans) == 1 and opt.upper().startswith(clean_ans.upper()):
            item["answer"] = opt
            item["options"] = cleaned_options
            return True, "Valid"

    return False, "Answer not in options list"

def _validate_question_topic_relevance(item, requested_topic, subject=""):
    """
    Validate that the generated question directly addresses the requested topic or subject domain.
    Supports arbitrary academic topics while rejecting cross-domain mismatches and hallucinations.
    """
    if not requested_topic:
        return True, "No topic specified"

    clean_t = requested_topic.lower().strip()
    clean_s = (subject or "").lower().strip()
    content = f"{item.get('prompt', '')} {item.get('explanation', '')} {' '.join(item.get('options', []))} {item.get('hint', '')}".lower()

    # 1. Direct substring match
    if clean_t in content:
        return True, "Exact topic match"

    # 2. Tokenize topic into significant words (excluding common stopwords)
    stopwords = {
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into",
        "through", "during", "before", "after", "above", "below", "the", "a", "an",
        "and", "or", "not", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "can", "could", "will", "would",
        "should", "what", "which", "how", "why", "when", "where", "basic", "basics"
    }
    raw_tokens = re.findall(r"\b[a-zA-Z0-9]{3,}\b", clean_t)
    significant_tokens = [tok for tok in raw_tokens if tok not in stopwords]

    # Check for direct word or root prefix match (e.g. 'struct' in 'structure', 'norm' in 'normalization')
    for tok in significant_tokens:
        if tok in content:
            return True, f"Matched topic keyword: {tok}"
        if len(tok) >= 5:
            stem = tok[:-1] if tok.endswith("s") or tok.endswith("e") else tok[:5]
            if stem in content:
                return True, f"Matched topic stem: {stem}"

    # 3. Known domain expansions for common curricula and umbrella academic topics
    DOMAIN_EXPANSIONS = {
        "data structure": ["list", "array", "tree", "node", "queue", "stack", "graph", "hash", "pointer", "heap", "complexity", "traversal", "search", "sort", "algorithm", "binary", "fifo", "lifo", "linked"],
        "data structures": ["list", "array", "tree", "node", "queue", "stack", "graph", "hash", "pointer", "heap", "complexity", "traversal", "search", "sort", "algorithm", "binary", "fifo", "lifo", "linked"],
        "dbms": ["database", "sql", "table", "normalization", "relation", "query", "key", "transaction", "acid", "index", "schema", "foreign key", "primary key", "normal form", "1nf", "2nf", "3nf", "bcnf", "relational"],
        "database": ["dbms", "sql", "table", "normalization", "relation", "query", "key", "transaction", "acid", "index", "schema", "foreign key", "primary key", "normal form", "relational"],
        "computer vision": ["vision", "image", "pixel", "convolution", "cnn", "visual", "object detection", "segmentation", "bounding box", "sobel", "filter", "kernel", "feature map", "iou", "pooling", "spatial"],
        "machine learning": ["overfitting", "underfitting", "gradient descent", "supervised", "unsupervised", "learning rate", "loss", "recall", "precision", "f1", "classifier", "regularization", "bias variance"],
        "deep learning": ["neural network", "backpropagation", "weights", "biases", "activation function", "relu", "cnn", "rnn", "lstm", "transformer", "attention"],
        "operating systems": ["process", "thread", "deadlock", "memory", "paging", "scheduling", "semaphore", "mutex", "kernel", "virtual memory", "cpu", "inter-process"],
        "linear equations": ["equation", "slope", "intercept", "variable", "linear", "substitution", "elimination"],
        "quadratic equations": ["quadratic", "discriminant", "roots", "parabola", "vertex", "factoring"],
        "arithmetic progressions": ["arithmetic progression", "common difference", "first term", "nth term", "sum of terms", "ap"],
        "trigonometry": ["sine", "cosine", "tangent", "hypotenuse", "angle", "elevation", "trigonometric", "cos", "sin", "tan"],
        "optics": ["reflection", "refraction", "mirror", "lens", "focal length", "ray diagram", "dispersion", "curvature"],
        "electricity": ["current", "voltage", "resistance", "resistor", "ohm", "circuit", "series", "parallel", "battery"],
        "chemical reactions": ["reaction", "precipitate", "combustion", "balanced", "reactants", "products", "oxidation", "acid"],
        "genetics": ["mendel", "genotype", "phenotype", "allele", "chromosome", "heterozygous", "homozygous", "f1", "f2"]
    }

    for topic_key, syns in DOMAIN_EXPANSIONS.items():
        if topic_key in clean_t or clean_t in topic_key:
            if any(syn in content for syn in syns):
                return True, f"Matched domain term for '{topic_key}'"

    # 4. For arbitrary academic topics, check if subject keywords align
    if clean_s and clean_s not in ("other", "general", "computer science", "mathematics"):
        s_tokens = [tok for tok in re.findall(r"\b[a-zA-Z]{4,}\b", clean_s) if tok not in stopwords]
        if any(stok in content for stok in s_tokens):
            return True, f"Matched subject keyword for '{clean_s}'"

    # 5. Short acronym or code (e.g. 'AI', 'CV', 'OS')
    short_tokens = re.findall(r"\b[a-zA-Z0-9]{2,}\b", clean_t)
    if any(re.search(rf"\b{re.escape(stk)}\b", content) for stk in short_tokens if len(stk) >= 2):
        return True, "Short token match"

    return False, f"Question did not address requested topic '{requested_topic}'"

def _extract_and_parse_json(raw):
    """
    Safely extract JSON array of question dicts from raw model output.
    Handles markdown fences (```json), leading/trailing prose, and partial truncations.
    """
    if not raw or not isinstance(raw, str):
        return None

    clean = raw.strip()
    if "```" in clean:
        clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean).strip()

    # 1. Direct parse attempt
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "questions" in parsed and isinstance(parsed["questions"], list):
            return parsed["questions"]
    except Exception:
        pass

    # 2. Extract substring between first '[' and last ']'
    start_idx = clean.find("[")
    end_idx = clean.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            parsed = json.loads(clean[start_idx:end_idx + 1])
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    # 3. Recover partial JSON if model was truncated before closing ']'
    if start_idx != -1:
        last_brace = clean.rfind("}")
        if last_brace > start_idx:
            recovered_str = clean[start_idx:last_brace + 1] + "\n]"
            try:
                parsed = json.loads(recovered_str)
                if isinstance(parsed, list) and len(parsed) > 0:
                    return parsed
            except Exception:
                pass

    return None

def run_diagnostic(
    gemini,
    subject,
    topic,
    level="Standard",
    count=4,
    stage="Class 10",
    curriculum="CBSE (Verified 2024-25)",
    previous_questions=None,
    timeout_ms=None
):
    """
    Run diagnostic question generation with:
    - Syllabus grounding without fabrication
    - Exam-style multi-step problem solving & reasoning
    - Distractors matching common misconceptions
    - Anti-repetition against previous learner attempts
    - Single-pass bounded execution for fast responsiveness
    - Curated offline fallback validation matching requested topic
    - Precise per-attempt and total duration metrics
    """
    global LAST_DIAGNOSTIC_METRICS

    t_total_start = time.time()
    count = max(3, min(10, int(count)))
    norm_previous = {normalize_question_prompt(q) for q in (previous_questions or []) if q}

    # 1. Syllabus lookup measurement (keyed by curriculum, stage, subject, topic)
    t_syl_start = time.time()
    syl = get_syllabus_context(stage, curriculum, subject, topic)
    t_syl_elapsed = time.time() - t_syl_start

    syllabus_info = (
        f"Verified Board Curriculum: {syl['curriculum']}\n"
        f"Syllabus Source: {syl['source']}\n"
        f"Unit/Chapters: {syl.get('chapters') or syl.get('unit')}\n"
        f"Target Learning Outcomes: {syl.get('outcomes')}\n"
        f"Board Exam Style: {syl.get('exam_style')}"
        if syl.get("verified") else
        f"Course Framework: {syl['curriculum']} ({syl['source']})\n"
        f"Topic Focus: {topic}\n"
        f"Target Outcomes: {syl.get('outcomes')}"
    )

    valid_questions = []
    collected_prompts = set()
    ai_elapsed = 0.0

    if gemini and getattr(gemini, "available", lambda: False)():
        # Build prompt with progression and anti-repetition instructions
        prev_examples = list(norm_previous)[:6]
        avoid_clause = ""
        if prev_examples:
            avoid_clause = f"IMPORTANT ANTI-REPETITION: Do NOT generate questions semantically similar to these previously seen questions:\n- " + "\n- ".join(prev_examples) + "\n"

        system_instruction = f"""You are an expert exam question creator designing a high-yield diagnostic assessment for a {stage} student.
{syllabus_info}
Target Subject: {subject}
Target Topic: {topic}
Difficulty Level: {level}
Number of Questions: {count}

PEDAGOGICAL & EXAM STANDARDS:
1. QUESTION STYLE: Create realistic exam-style questions requiring application, multi-step calculations, data/diagram interpretation, or causal reasoning.
2. DIFFICULTY PROGRESSION: Progress from core principles to multi-step reasoning and edge conditions.
3. DISTRACTORS: All 4 choices must be plausible. Incorrect options should reflect typical student misconceptions.
4. ACCURACY: There must be EXACTLY ONE unambiguous, mathematically/scientifically indisputable correct answer.
5. EXPLANATION: Concise worked explanation (1-2 sentences) showing why the answer is correct and why other options fail.
6. HINT: Offer a constructive clue without giving the answer away.
7. MISTAKE_TYPE: Tag each question with one of: conceptual, calculation, misread, recall, incomplete.
8. TOPIC SPECIFICITY: Every question must directly test concepts, mechanisms, algorithms, problem-solving, or principles of the requested topic '{topic}'. Explicitly reference key terms or principles of '{topic}' in the question prompt or explanation.

{avoid_clause}
RETURN FORMAT: Return ONLY a valid JSON array of objects with keys:
- prompt (string)
- options (array of 4 distinct choices, plain text without letter prefixes)
- answer (string, exactly matching one choice in options)
- explanation (concise 1-2 sentence string)
- hint (string)
- mistake_type (one of: conceptual, calculation, misread, recall, incomplete)"""

        # Bounded generation pass with end-to-end latency budget
        t_ai_start = time.time()
        output_tokens = max(2048, count * 600)
        try:
            raw, _ = gemini.generate_text(
                system_instruction,
                max_output_tokens=output_tokens,
                timeout_ms=timeout_ms
            )
        except TypeError:
            raw, _ = gemini.generate_text(
                system_instruction,
                max_output_tokens=output_tokens
            )
        ai_elapsed = round(time.time() - t_ai_start, 3)

        if raw:
            try:
                parsed = _extract_and_parse_json(raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        ok_struct, _ = _validate_question_structure(item)
                        if not ok_struct:
                            continue

                        # Validate question topic relevance before accepting
                        ok_topic, _ = _validate_question_topic_relevance(item, topic, subject)
                        if not ok_topic:
                            continue

                        norm_p = normalize_question_prompt(item["prompt"])
                        # Anti-repetition check against DB history and current batch
                        if norm_p in norm_previous or norm_p in collected_prompts:
                            continue
                        item["id"] = f"q_{uuid4().hex[:8]}"
                        item.setdefault("hint", "")
                        item.setdefault("mistake_type", "conceptual")
                        valid_questions.append(item)
                        collected_prompts.add(norm_p)
                        if len(valid_questions) >= count:
                            break
            except Exception:
                pass

        if len(valid_questions) >= count or len(valid_questions) >= 3:
            final_qs = valid_questions[:count] if len(valid_questions) >= count else valid_questions
            alignment_status = "AI-generated • Verified Syllabus Aligned" if syl.get("verified") else "AI-generated • Topic-based (not syllabus-verified)"
            status_text = alignment_status if len(valid_questions) >= count else f"{alignment_status} ({len(valid_questions)} unique questions)"

            gemini_metrics = getattr(gemini, "last_metrics", {})
            LAST_DIAGNOSTIC_METRICS = {
                "syllabus_lookup_s": round(t_syl_elapsed, 6),
                "ai_generation_s": ai_elapsed,
                "fallback_lookup_s": 0.0,
                "total_elapsed_s": round(time.time() - t_total_start, 3),
                "source_used": "ai",
                "question_count": len(final_qs),
                "api_attempts": gemini_metrics.get("attempts", []),
                "model": getattr(gemini, "model", "gemini-3.8-flash"),
                "timed_out": False
            }
            return final_qs, status_text

    # Fallback path: curated built-in questions genuinely matching topic
    t_fb_start = time.time()
    bank = _get_fallback_bank(subject, topic, level)
    if not bank or len(bank) < 3:
        LAST_DIAGNOSTIC_METRICS = {
            "syllabus_lookup_s": round(t_syl_elapsed, 6),
            "ai_generation_s": ai_elapsed,
            "fallback_lookup_s": round(time.time() - t_fb_start, 6),
            "total_elapsed_s": round(time.time() - t_total_start, 3),
            "source_used": "none",
            "question_count": 0,
            "api_attempts": getattr(gemini, "last_metrics", {}).get("attempts", []) if gemini else [],
            "model": getattr(gemini, "model", "gemini-3.8-flash") if gemini else "offline",
            "timed_out": getattr(gemini, "last_metrics", {}).get("timeout_occurred", False) if gemini else False
        }
        return [], "We couldn't prepare verified questions for this topic right now. Please try again. No offline fallback questions match this custom topic. Please check your connection and try again in a few moments."

    fallback_questions = []
    fresh_bank = [item for item in bank if normalize_question_prompt(item["prompt"]) not in norm_previous]
    candidate_pool = fresh_bank if len(fresh_bank) >= 3 else bank

    for item in candidate_pool:
        clone = dict(item)
        clone["id"] = f"q_{uuid4().hex[:8]}"
        fallback_questions.append(clone)
        if len(fallback_questions) >= count:
            break

    # If count requested is larger than available unique questions in bank,
    # keep the unique verified questions rather than filling with unrelated questions
    final_fallback = fallback_questions
    t_fb_elapsed = time.time() - t_fb_start

    if len(final_fallback) < count:
        status_note = f"Built-in curated questions (offline fallback · {len(final_fallback)} verified questions available)"
    else:
        status_note = "Built-in curated questions (offline fallback)"

    if syl.get("verified"):
        status_note += f" · Core alignment: {syl['curriculum']}"

    gemini_metrics = getattr(gemini, "last_metrics", {}) if gemini else {}
    LAST_DIAGNOSTIC_METRICS = {
        "syllabus_lookup_s": round(t_syl_elapsed, 6),
        "ai_generation_s": ai_elapsed,
        "fallback_lookup_s": round(t_fb_elapsed, 6),
        "total_elapsed_s": round(time.time() - t_total_start, 3),
        "source_used": "fallback",
        "question_count": len(final_fallback),
        "api_attempts": gemini_metrics.get("attempts", []),
        "model": getattr(gemini, "model", "gemini-3.8-flash") if gemini else "offline",
        "timed_out": gemini_metrics.get("timeout_occurred", False)
    }
    return final_fallback, status_note
