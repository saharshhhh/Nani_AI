# imports

from dotenv import load_dotenv
from openai import OpenAI
from openai import RateLimitError, NotFoundError
import json
import os
import requests
from pypdf import PdfReader
import gradio as gr



# The usual start
load_dotenv(override=True)
gemini=os.getenv('GOOGLE_API_KEY')
openai = OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",api_key=gemini)



# For pushover

pushover_user = os.getenv("PUSHOVER_USER")
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_url = "https://api.pushover.net/1/messages.json"

if pushover_user:
    print(f"Pushover user found and starts with {pushover_user[0]}")
else:
    print("Pushover user not found")

if pushover_token:
    print(f"Pushover token found and starts with {pushover_token[0]}")
else:
    print("Pushover token not found")



def push(message):
    print(f"Push: {message}")
    payload = {"user": pushover_user, "token": pushover_token, "message": message}
    requests.post(pushover_url, data=payload)



def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"Recording interest from {name} with email {email} and notes {notes}")
    return {"recorded": "ok"}



def record_unknown_question(question):
    push(f"Recording {question} asked that I couldn't answer")
    return {"recorded": "ok"}



record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address of this user"
            },
            "name": {
                "type": "string",
                "description": "The user's name, if they provided it"
            },
            "notes": {
                "type": "string",
                "description": "Any additional information about the conversation that's worth recording to give context"
            }
        },
        "required": ["email"],
        "additionalProperties": False
    }
}



record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered as you didn't know the answer",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question that couldn't be answered"
            },
        },
        "required": ["question"],
        "additionalProperties": False
    }
}



tools = [{"type": "function", "function": record_user_details_json},
        {"type": "function", "function": record_unknown_question_json}]



tools



# This function can take a list of tool calls, and run them. This is the IF statement!!

def handle_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Tool called: {tool_name}", flush=True)

        # THE BIG IF STATEMENT!!!
        
        if tool_name == "record_user_details":
            result = record_user_details(**arguments)
        elif tool_name == "record_unknown_question":
            result = record_unknown_question(**arguments)

        results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
    return results



globals()["record_unknown_question"]("this is a really hard question")



globals()["record_user_details"]("A new user is interested")



# This is a more elegant way that avoids the IF statement.

def handle_tool_calls(tool_calls):
    results = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        print(f"Tool called: {tool_name}", flush=True)
        tool = globals().get(tool_name)
        result = tool(**arguments) if tool else {}
        results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
    return results



reader = PdfReader("Nani.pdf")
about = ""
for page in reader.pages:
    text = page.extract_text()
    if text:
        about += text

with open("me/summary.txt", "r", encoding="utf-8") as f:
    summary = f.read()

name = "Nani"



system_prompt = f"You are acting as {name}. You are answering questions on {name}\
particularly questions related to {name}'s career, background, skills and experience in movies. \
Your responsibility is to represent {name} for interactions as faithfully as possible. \
You are given a summary of {name}'s background and wikipedia information which you can use to answer questions. \
Be casual and engaging, as if talking to a fan of yours or an influenced person of yours. \
Imitate Nani as much as possible. \
If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool. "

system_prompt += f"\n\n## Summary:\n{summary}\n\n## wiki source:\n{about}\n\n"
system_prompt += f"With this context, please chat with the user, always staying in character as {name}."




def chat(message, history):
    try:
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message}]
        done = False
        
        # Try different models in order of preference
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
        model_index = 0
        response = None
        
        while not done:
            # This is the call to the LLM - see that we pass in the tools json
            try:
                response = openai.chat.completions.create(model=models_to_try[model_index], messages=messages, tools=tools)
            except NotFoundError:
                # Try next model if current one doesn't exist
                model_index += 1
                if model_index >= len(models_to_try):
                    return "Error: No available Gemini models found. Please check your API configuration."
                continue
            except RateLimitError as e:
                return f"I'm sorry, but I've hit the rate limit for the Gemini API. Please wait a few minutes and try again. You can check your usage at https://ai.dev/usage?tab=rate-limit"
            except Exception as e:
                return f"I encountered an error while calling the API: {str(e)}. Please try again later."

            if not response or not response.choices:
                return "Error: Received an invalid response from the API. Please try again."

            finish_reason = response.choices[0].finish_reason
            
            # If the LLM wants to call a tool, we do that!
             
            if finish_reason=="tool_calls":
                message = response.choices[0].message
                tool_calls = message.tool_calls
                results = handle_tool_calls(tool_calls)
                messages.append(message)
                messages.extend(results)
            else:
                done = True
        
        # Ensure we always return a string, never None
        if response and response.choices and response.choices[0].message:
            content = response.choices[0].message.content
            return content if content is not None else "I received a response but it was empty. Please try again."
        else:
            return "Error: Could not get a valid response from the API. Please try again."
    except Exception as e:
        return f"I encountered an error: {str(e)}. Please try again later."



gr.ChatInterface(chat, type="messages").launch()


