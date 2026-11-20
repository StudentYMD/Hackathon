import os
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# 1. Define the exact JSON structure we want the AI to return
class ActionItem(BaseModel):
    task_title: str = Field(
        description="Short, clear action-oriented title for the Trello card."
    )
    owner: Optional[str] = Field(
        default=None,
        description="Name of the person responsible. Leave null if unassigned or vague (e.g., 'someone')."
    )
    deadline: Optional[str] = Field(
        default=None,
        description="Due date or timeframe mentioned (e.g., 'Friday', 'Tomorrow 5 PM'). Leave null if not specified."
    )
    priority: str = Field(
        description="Estimated priority based on urgency: 'High', 'Medium', or 'Low'."
    )
    is_ambiguous: bool = Field(
        description="Set to True if either the owner is missing/unclear OR the deadline is missing/vague."
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="If is_ambiguous is True, write a short question to ask the user (e.g., 'Who should own this task and when is it due?')."
    )
    reasoning: str = Field(
        description="Brief explanation of why this was extracted as a commitment and why it was marked clear or ambiguous."
    )

class MeetingExtraction(BaseModel):
    meeting_summary: str = Field(
        description="A 2-sentence summary of the overall meeting context."
    )
    action_items: List[ActionItem] = Field(
        description="List of actionable commitments extracted from the transcript. Ignore general chatter."
    )

# 2. The main extraction function
def extract_tasks_from_transcript(transcript: str, api_key: str) -> dict:
    client = genai.Client(api_key=api_key.strip())

    system_instruction = """
    You are an intelligent Meeting-to-Action AI Agent. Analyze the provided meeting transcript and extract ONLY genuine, actionable commitments and decisions.
    
    Rules:
    1. IGNORE casual conversation, jokes, brainstorming ideas that were not agreed upon, and status updates on already-finished work.
    2. IDENTIFY Task Ownership: Assign the exact person who agreed to do the task. If someone says "we need to fix X" without assigning a name, set owner to null.
    3. FLAG AMBIGUITY (Human-in-the-Loop): If a task has no clear owner OR no clear deadline, you MUST set 'is_ambiguous' to True and provide a helpful 'clarification_question'.
    4. EXPLAIN REASONING: Always explain your logic in the 'reasoning' field (e.g., "Extracted because Rahul explicitly committed to deploying the API by Friday.").
    """

    # Ordered by speed and free-tier availability to avoid 503 High Demand congestion
    candidate_models = [
        "gemini-4-hydrogen",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    ]

    last_error = None
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=f"Analyze this meeting transcript:\n\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=MeetingExtraction,
                    temperature=0.1,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            last_error = e
            # If overloaded (503) or slow, silently move to the next fast model
            continue

    raise RuntimeError(f"All Gemini models are currently busy. Last error: {last_error}")

    # Parse and return as a standard Python dictionary
    return json.loads(response.text)

# 3. Quick test block (Run `python extractor.py` to test!)
if __name__ == "__main__":
    # Paste your Gemini API key here just to test
    xyz = "xyz"

    sample_transcript = """
    Ananya: Hey everyone, hope you had a good weekend! Ready to get started?
    Rahul: Yeah, let's dive in. First, the login page is crashing on mobile. I'll fix the CSS bug and push it to GitHub by tomorrow at 6 PM.
    Ananya: Awesome, thanks Rahul. Also, we really need someone to write the pitch deck slides soon, maybe next week?
    Vikram: Agreed. Oh, and I will set up the Supabase database tables tonight before 11 PM so the backend is ready.
    Ananya: Sounds great! Let's wrap up here.
    """

    result = extract_tasks_from_transcript(sample_transcript, xyz)
    print(json.dumps(result, indent=2))
