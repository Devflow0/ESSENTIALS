import sqlite3
import pandas as pd
from datetime import datetime
import streamlit as st
from db_security import decrypt_data

from groq import Groq

# Setup your API Key
API_KEY = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=API_KEY)

def get_ai_daily_summary(custom_prompt: str = None):
    """
    Returns an AI response about vehicle movements.
    - If custom_prompt is None: generates today's standard daily summary.
    - If custom_prompt is provided: answers the user's specific question using
      the full historical movement log as context.
    """
    db_name = 'alpr_data.db'
    today = datetime.now().strftime('%Y-%m-%d')

    with sqlite3.connect(db_name) as conn:
        if custom_prompt:
            # For custom queries, pull ALL records so the AI can look up any vehicle
            df = pd.read_sql_query("SELECT * FROM movements ORDER BY timestamp DESC", conn)
        else:
            df = pd.read_sql_query(
                "SELECT * FROM movements WHERE date(timestamp) = ?",
                conn, params=(today,)
            )
        if not df.empty:
            df['plate'] = df['plate'].apply(decrypt_data)

    if df.empty:
        return "No vehicle movement data found in the database."

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    if custom_prompt:
        # Build a compact data context (last 200 rows to stay within token limits)
        context_rows = df.head(200)[['timestamp', 'plate', 'event']].copy()
        context_rows['timestamp'] = context_rows['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
        data_context = context_rows.to_string(index=False)

        prompt = f"""You are a professional vehicle security AI analyst with access to the following movement log:

{data_context}

Using ONLY the data above, answer this question as clearly and helpfully as possible:
{custom_prompt}

If the data does not contain enough information to answer the question, say so explicitly."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a professional vehicle security AI analyst. Answer only based on the data provided."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    # --- Default: daily summary ---
    total_moves = len(df)
    entries = len(df[df['event'] == 'ENTRY'])
    exits = len(df[df['event'] == 'EXIT'])
    busiest_hour = df['timestamp'].dt.hour.mode()[0] if not df.empty else "N/A"
    frequent_visitor = df['plate'].value_counts().idxmax() if not df.empty else "None"

    prompt = f"""
    As a Vehicle Security AI, summarize today's vehicle traffic:
    - Total Movements: {total_moves}
    - Entries: {entries}, Exits: {exits}
    - Peak Traffic Hour: {busiest_hour}:00
    - Most Frequent Vehicle: {frequent_visitor}

    Provide a professional 3-sentence summary highlighting any potential security
    concerns or operational bottlenecks for management.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You are a professional Vehicle Security AI analyst."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def process_meeting_audio(audio_bytes):
    """processing for transcription and summary."""
    try:
        # 1. Transcribe the audio using Whisper
        transcription = client.audio.transcriptions.create(
            file=("meeting.wav", audio_bytes),
            model="whisper-large-v3",
            response_format="text"
        )
        
        # 2. Summarize the transcript
        summary_prompt = f"""
        You are a professional hotel executive assistant. 
        Based on the following meeting transcript:
        
        {transcription}
        
        1. Provide a 'Executive Summary'.
        2. List 'Action Items' with responsible parties if mentioned.
        Format the output clearly using Markdown.
        """
        
        summary_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": summary_prompt}]
        )
        
        return f"### Transcription\n{transcription}\n\n---\n\n{summary_response.choices[0].message.content}"
    except Exception as e:
        return f"❌ AI Processing Error: {str(e)}"