import streamlit as st
import fitz  # PyMuPDF
import sqlite3
import json
import google.generativeai as genai
from dotenv import load_dotenv
import os

# Configure Gemini API (ensure your .env file contains GEMINI_API_KEY)
load_dotenv()
my_api_key = os.getenv("GEMINI_API_KEY")
if not my_api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in your .env file.")
genai.configure(api_key=my_api_key)
def extract_text_from_pdf(file):
    doc = fitz.open(stream=file.getvalue(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# Function to store data in SQLite
def store_data(candidate_name, resume_text, jd_title, jd_text, questions=None):
    conn = sqlite3.connect("interview_db.sqlite")
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            resume_text TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS question_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER,
            job_id INTEGER,
            questions TEXT,
            FOREIGN KEY(candidate_id) REFERENCES candidates(id),
            FOREIGN KEY(job_id) REFERENCES job_descriptions(id)
        )
    """)
    
    # Insert candidate and JD data
    cursor.execute("INSERT INTO candidates (name, resume_text) VALUES (?, ?)", (candidate_name, resume_text))
    candidate_id = cursor.lastrowid
    cursor.execute("INSERT INTO job_descriptions (title, description) VALUES (?, ?)", (jd_title, jd_text))
    job_id = cursor.lastrowid
    
    if questions:
        questions_json = json.dumps(questions)
        cursor.execute("INSERT INTO question_sets (candidate_id, job_id, questions) VALUES (?, ?, ?)", 
                       (candidate_id, job_id, questions_json))
    
    conn.commit()
    conn.close()
    return candidate_id, job_id

# Function to update questions in SQLite
def update_questions(candidate_id, job_id, questions):
    conn = sqlite3.connect("interview_db.sqlite")
    cursor = conn.cursor()
    questions_json = json.dumps(questions)
    cursor.execute("UPDATE question_sets SET questions = ? WHERE candidate_id = ? AND job_id = ?", 
                   (questions_json, candidate_id, job_id))
    conn.commit()
    conn.close()

# Function to generate questions using Gemini API
def generate_questions(resume_text, jd_text, num_questions, custom_prompt=None):
    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = f"""
        You are an expert recruiter tasked with creating interview questions to assess a candidate's fit for a specific role. 
        Below are the candidate's resume and the job description for the role. Your goal is to generate {num_questions} 
        tailored interview questions that:
        - Evaluate the candidate’s relevant skills, experience, and achievements from the resume against the job requirements.
        - Highlight specific areas of fitment or gaps between the resume and job description.
        - Include a mix of technical, behavioral, and situational questions relevant to the role.
        - Are concise, specific, and directly tied to the provided job description and resume content.

        Job Description:
        "{jd_text}"

        Candidate Resume:
        "{resume_text}"

        Provide the questions as a numbered list (e.g., 1., 2., etc.).
        """
    
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    questions = [q.strip() for q in response.text.split("\n") if q.strip().startswith(tuple(str(i) + "." for i in range(1, num_questions + 1)))]
    return questions

# Streamlit UI
st.title("Interview Question Generator")

# Two-column layout
col1, col2 = st.columns(2)

# Column 1: Resume Upload and Slider
with col1:
    st.subheader("Upload Resume & Settings")
    candidate_name = st.text_input("Candidate Name", "John Doe")
    resume = st.file_uploader("Upload Resume (PDF)", type=["pdf"], key="resume")
    num_questions = st.slider("Number of Questions", min_value=1, max_value=10, value=5)

# Column 2: Job Description, Questions Display, and Regeneration
with col2:
    st.subheader("Job Description & Questions")
    jd = st.file_uploader("Upload Job Description (PDF)", type=["pdf"], key="jd")
    
    if "questions" not in st.session_state:
        st.session_state.questions = []
        st.session_state.candidate_id = None
        st.session_state.job_id = None
    
    # Generate Questions Button
    if st.button("Generate Questions"):
        if candidate_name and resume and jd:
            resume_text = extract_text_from_pdf(resume)
            jd_text = extract_text_from_pdf(jd)
            candidate_id, job_id = store_data(candidate_name, resume_text, "Job Title", jd_text)
            questions = generate_questions(resume_text, jd_text, num_questions)
            
            # Store the generated questions in the database
            update_questions(candidate_id, job_id, questions)
            
            # Update session state
            st.session_state.questions = questions
            st.session_state.candidate_id = candidate_id
            st.session_state.job_id = job_id
        else:
            st.error("Please provide all required inputs.")
    # Display Questions
    if st.session_state.questions:
        st.write("Generated Questions:")
        for q in st.session_state.questions:
            st.write(q)
    
    # Custom Prompt for Regeneration
    custom_prompt = st.text_area("Edit Prompt to Regenerate Questions (Optional)", 
                                 "Enter a custom prompt here to regenerate questions...", height=200)
    if st.button("Regenerate Questions"):
        if custom_prompt.strip() and st.session_state.candidate_id and st.session_state.job_id:
            resume_text = extract_text_from_pdf(resume)
            jd_text = extract_text_from_pdf(jd)
            questions = generate_questions(resume_text, jd_text, num_questions, custom_prompt)
            st.session_state.questions = questions
            update_questions(st.session_state.candidate_id, st.session_state.job_id, questions)
            st.success("Questions regenerated successfully!")
        else:
            st.error("Please provide a custom prompt and ensure questions were generated first.")
