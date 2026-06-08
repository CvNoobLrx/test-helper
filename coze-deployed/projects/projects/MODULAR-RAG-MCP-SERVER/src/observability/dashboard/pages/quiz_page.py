"""Dashboard page: Quiz – interactive quiz interface."""

from __future__ import annotations

import json
import streamlit as st
from typing import List, Dict, Any, Optional

from src.core.settings import load_settings, resolve_path
from src.core.types import QuizQuestion, MasteryRecord
from src.ingestion.storage.knowledge_point_index import KnowledgePointIndex
from src.ingestion.storage.mastery_store import MasteryStore
from src.ingestion.storage.spaced_repetition import calculate_next_review
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.base_llm import Message
import re


def render() -> None:
    st.title("Quiz")
    st.markdown("Test your knowledge with generated quiz questions.")

    try:
        settings = load_settings()
    except Exception as e:
        st.error(f"Failed to load settings: {e}")
        return

    kp_index = KnowledgePointIndex(
        index_dir=str(resolve_path("data/db/knowledge_points"))
    )

    data_dir = "data/db/mastery"
    if settings.mastery:
        data_dir = settings.mastery.data_dir
    mastery_store = MasteryStore(data_dir=str(resolve_path(data_dir)))

    # Collection selector
    collections_dir = resolve_path("data/db/knowledge_points")
    collections = []
    if collections_dir.exists():
        for f in collections_dir.iterdir():
            if f.suffix == ".json" and f.stem.endswith("_kp"):
                collections.append(f.stem.replace("_kp", ""))

    if not collections:
        st.info("No knowledge points found. Ingest documents first.")
        return

    collection = st.sidebar.selectbox("Collection", collections, key="quiz_collection")

    # Quiz configuration
    col1, col2 = st.columns(2)
    with col1:
        num_questions = st.slider("Number of questions", 1, 20, 5, key="quiz_num")
    with col2:
        difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], key="quiz_diff")

    # Generate quiz button
    if st.button("Generate Quiz", key="quiz_generate"):
        all_kps = kp_index.get_by_collection(collection)
        if not all_kps:
            st.warning("No knowledge points available.")
            return

        # Select KPs (prioritize low mastery)
        all_records = mastery_store.get_all_records(collection)
        record_map = {r.knowledge_point_id: r for r in all_records}

        def sort_key(kp):
            rec = record_map.get(kp["id"])
            if rec is None:
                return (0, 0)
            return (rec.correct_rate, rec.review_count)

        all_kps.sort(key=sort_key)
        selected_kps = all_kps[:num_questions]

        with st.spinner("Generating quiz questions..."):
            questions = _generate_questions(settings, selected_kps, num_questions, difficulty)

        if questions:
            st.session_state["quiz_questions"] = questions
            st.session_state["quiz_answers"] = {}
            st.session_state["quiz_submitted"] = False
            st.session_state["quiz_collection"] = collection
        else:
            st.error("Failed to generate quiz questions. Please try again.")

    # Display quiz
    questions = st.session_state.get("quiz_questions", [])
    if not questions:
        st.info("Click 'Generate Quiz' to start.")
        return

    st.subheader(f"Quiz ({len(questions)} questions)")

    answers = st.session_state.get("quiz_answers", {})
    submitted = st.session_state.get("quiz_submitted", False)

    for i, q in enumerate(questions):
        st.markdown(f"**Q{i+1}. [{q.question_type}]** {q.question_text}")

        if q.question_type == "mcq" and q.options:
            if submitted:
                # Show results
                user_answer = answers.get(q.id, "")
                is_correct = user_answer == q.correct_answer
                for opt in q.options:
                    prefix = ""
                    if opt == q.correct_answer:
                        prefix = ":green[✓] "
                    elif opt == user_answer and not is_correct:
                        prefix = ":red[✗] "
                    st.markdown(f"  {prefix}{opt}")
            else:
                answer = st.radio(
                    "Select answer",
                    q.options,
                    key=f"quiz_q_{i}",
                    label_visibility="collapsed",
                )
                answers[q.id] = answer

        elif q.question_type == "true_false":
            options = ["True", "False"]
            if submitted:
                user_answer = answers.get(q.id, "")
                is_correct = user_answer == q.correct_answer
                for opt in options:
                    prefix = ""
                    if opt.lower() == q.correct_answer.lower():
                        prefix = ":green[✓] "
                    elif opt == user_answer and not is_correct:
                        prefix = ":red[✗] "
                    st.markdown(f"  {prefix}{opt}")
            else:
                answer = st.radio(
                    "Select",
                    options,
                    key=f"quiz_q_{i}",
                    label_visibility="collapsed",
                )
                answers[q.id] = answer

        else:  # short_answer
            if submitted:
                user_answer = answers.get(q.id, "")
                st.markdown(f"  Your answer: {user_answer}")
                st.markdown(f"  Correct answer: :green[{q.correct_answer}]")
            else:
                answer = st.text_input("Your answer", key=f"quiz_q_{i}")
                answers[q.id] = answer

        if submitted and q.explanation:
            st.markdown(f"  *Explanation: {q.explanation}*")
        st.divider()

    # Submit button
    if not submitted:
        if st.button("Submit Quiz", key="quiz_submit"):
            st.session_state["quiz_answers"] = answers
            st.session_state["quiz_submitted"] = True

            # Record results
            _record_results(mastery_store, questions, answers, collection)
            st.rerun()
    else:
        # Show score
        correct = 0
        for q in questions:
            user_answer = answers.get(q.id, "")
            if q.question_type == "mcq":
                if user_answer == q.correct_answer:
                    correct += 1
            elif q.question_type == "true_false":
                if user_answer.lower() == q.correct_answer.lower():
                    correct += 1
            else:
                if user_answer.strip().lower() in q.correct_answer.lower():
                    correct += 1

        score = correct / len(questions) if questions else 0
        st.metric("Score", f"{correct}/{len(questions)} ({score*100:.0f}%)")

        if st.button("New Quiz", key="quiz_new"):
            del st.session_state["quiz_questions"]
            del st.session_state["quiz_answers"]
            del st.session_state["quiz_submitted"]
            st.rerun()


def _generate_questions(
    settings,
    kps: List[Dict[str, Any]],
    num_questions: int,
    difficulty: str,
) -> List[QuizQuestion]:
    try:
        llm = LLMFactory.create(settings)
    except Exception as e:
        return []

    prompt_path = resolve_path("config/prompts/quiz_generation.txt")
    if not prompt_path.exists():
        return []

    prompt_template = prompt_path.read_text(encoding="utf-8")
    kp_text = "\n".join(
        f"- ID: {kp['id']}, 分类: {kp.get('category', 'general')}, "
        f"重要性: {kp.get('importance', 3)}, 内容: {kp['text']}"
        for kp in kps
    )

    formatted_prompt = prompt_template.replace("{knowledge_points}", kp_text)
    formatted_prompt = formatted_prompt.replace("{num_questions}", str(num_questions))
    formatted_prompt = formatted_prompt.replace("{difficulty}", difficulty)

    try:
        messages = [Message(role="user", content=formatted_prompt)]
        response = llm.chat(messages)

        response_text = response
        if hasattr(response, "content"):
            response_text = response.content
        elif not isinstance(response, str):
            response_text = str(response)

        json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if not json_match:
            return []

        raw_questions = json.loads(json_match.group())
        kp_ids = {kp["id"] for kp in kps}
        questions = []

        for i, raw in enumerate(raw_questions):
            if not isinstance(raw, dict) or "question_text" not in raw:
                continue

            kp_id = raw.get("knowledge_point_id", "")
            if kp_id not in kp_ids and kps:
                kp_id = kps[i % len(kps)]["id"]

            questions.append(QuizQuestion(
                id=f"q_{i}",
                knowledge_point_id=kp_id,
                question_type=raw.get("question_type", "short_answer"),
                question_text=raw["question_text"],
                options=raw.get("options", []),
                correct_answer=raw.get("correct_answer", ""),
                explanation=raw.get("explanation", ""),
            ))

        return questions
    except Exception:
        return []


def _record_results(
    mastery_store: MasteryStore,
    questions: List[QuizQuestion],
    answers: Dict[str, str],
    collection: str,
) -> None:
    min_ef = 1.3
    try:
        settings = load_settings()
        if settings.mastery:
            min_ef = settings.mastery.min_ease_factor
    except Exception:
        pass

    for q in questions:
        user_answer = answers.get(q.id, "")
        is_correct = False

        if q.question_type == "mcq":
            is_correct = user_answer == q.correct_answer
        elif q.question_type == "true_false":
            is_correct = user_answer.lower() == q.correct_answer.lower()
        else:
            is_correct = user_answer.strip().lower() in q.correct_answer.lower()

        quality = 4 if is_correct else 1

        record = mastery_store.get_record(q.knowledge_point_id, collection)
        if record is None:
            record = MasteryRecord(
                knowledge_point_id=q.knowledge_point_id,
                collection=collection,
            )

        updated = calculate_next_review(quality, record, min_ease_factor=min_ef)
        mastery_store.update_record(updated)
