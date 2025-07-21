from dotenv import load_dotenv
import os
from google import genai
from google.genai.types import GenerateContentConfig
import json
from pypdf import PdfReader
import gradio as gr
import smtplib

load_dotenv(override=True)
api_key=os.getenv("GOOGLE_API_KEY")

def push(message, reason):
    print(f"Push: {reason}\n{message}")

    clone_mail = os.getenv("CLONE_EMAIL")
    clone_password = os.getenv("CLONE_PASSWORD")

    print(f"Email: {clone_mail}")
    print(f"Password: {'*' * len(clone_password) if clone_password else 'None'}")
    
    if not clone_mail or not clone_password:
        print("Error: CLONE_EMAIL or CLONE_PASSWORD not found in environment variables")
        print("Please create a .env file with CLONE_EMAIL and CLONE_PASSWORD")
        return
    
    try:
        mail=smtplib.SMTP("smtp.gmail.com")
        mail.starttls()
        mail.login(user=clone_mail, password=clone_password)
        mail.sendmail(
            from_addr=clone_mail, 
            to_addrs= "rumesefia@gmail.com", 
            msg=f"Subject:{reason}\n\n{message}"
            )
        mail.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error sending email: {e}")

def record_user_details(email, name="Name not provided", notes="notes not provided"):
    push(f"Recording interest from {name} with email {email} and notes {notes}", "Recording User Details")
    return {"recorded": "ok"}

def record_unknown_question(question):
    push(f"Recording {question} that I don't know the answer to", "Recording Unknown Question")
    return {"recorded": "ok"}

tools_list = [
    {
      "function_declarations": [
        {
          "name": "record_user_details",
          "description": "Records user details including email, name, and notes. Used for capturing user interest or contact information.",
          "parameters": {
            "type": "OBJECT",
            "properties": {
              "email": {
                "type": "STRING",
                "description": "The user's email address (required)."
              },
              "name": {
                "type": "STRING",
                "description": "The user's name (optional, defaults to 'Name not provided')."
              },
              "notes": {
                "type": "STRING",
                "description": "Any additional notes or details provided by the user (optional, defaults to 'notes not provided')."
              }
            },
            "required": ["email"]
          }
        }
      ]
    },
    {
      "function_declarations": [
        {
          "name": "record_unknown_question",
          "description": "Records a question that the Gemini agent does not know the answer to, for future reference or training.",
          "parameters": {
            "type": "OBJECT",
            "properties": {
              "question": {
                "type": "STRING",
                "description": "The question that the agent could not answer."
              }
            },
            "required": ["question"]
          }
        }
      ]
    }
]

class Me:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.name = "Sefia Oghenerume"
        reader = PdfReader("Profile.pdf")
        self.linkedin = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                self.linkedin += text
        resume_reader = PdfReader("resume.pdf")
        self.resume = ""
        for page in resume_reader.pages:
            text = page.extract_text()
            if text:
                self.resume += text
        with open("summary.txt", "r", encoding="utf-8") as file:
            self.summary = file.read()
        self.system_prompt = self.prompt()

    def prompt(self):
        system_prompt = f"You are acting as {self.name}. You are answering questions on {self.name}'s website, \
            particularly questions related to {self.name}'s career, background, skills and experience. \
            Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. \
            You are given a summary of {self.name}'s background, current professional resume, and LinkedIn profile which you can use to answer questions. \
            Be professional and engaging, as if talking to a potential client or future employer who came across the website. \
            If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer, even if it's about something trivial or unrelated to career. \
            If the user is engaging in discussion, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool."
        system_prompt += f"Respond in a natural, conversational, and engaging tone. Avoid using bullet points, markdown formatting, or lists, \
            unless explicitly requested or required to drive home a point. Write as if you are having a friendly, semi-formal \
            chat with the user—use contractions, vary your sentence structure, and keep your language warm and personable."
        system_prompt += f"You are to represent the engineer of this agent and the author of this prompt {self.name} \
            prioritize the information in the summary although not openly divulge it to the user. \
            it is simply a guide to give context of the person you are deployed to represent. \
            Following the summary, prioritise information in the resume, followed by the github stated in the summary, then the linkedin last"
        system_prompt += f"With this context, please chat with the user, always staying in character as {self.name}."
        system_prompt += f"\n\n## Summary:\n{self.summary}\n\n## LinkedIn Profile:\n{self.linkedin}\n\n## Resume:\n{self.resume}\n\n"
        return system_prompt

    def handle_tool_calls(self, tool_calls):
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)
            tool = globals().get(tool_name)
            result = tool(**arguments) if tool else {}
            results.append({"role": "tool","content": json.dumps(result),"tool_call_id": tool_call.id})
        return results

    def chat(self, message, history):
        config = GenerateContentConfig(tools=tools_list)
        gemini_messages = []
        if self.system_prompt:
            gemini_messages.append({"role": "user", "parts": [{"text": self.system_prompt}]})
        for h_msg in history:
            if h_msg["role"] == "user":
                gemini_messages.append({"role": "user", "parts": [{"text": h_msg["content"]}]})
            elif h_msg["role"] == "assistant":
                parts = []
                if "content" in h_msg and h_msg["content"]:
                    parts.append({"text": h_msg["content"]})
                if "tool_calls" in h_msg and h_msg["tool_calls"]:
                    for tc in h_msg["tool_calls"]:
                        parts.append({"function_call": {"name": tc.function.name, "args": json.loads(tc.function.arguments)}})
                gemini_messages.append({"role": "model", "parts": parts})
            elif h_msg["role"] == "tool":
                gemini_messages.append(h_msg)

        gemini_messages.append({"role": "user", "parts": [{"text": message}]})

        done = False
        while not done:
            response = self.client.models.generate_content(model="gemini-2.0-flash", contents=gemini_messages, config=config)
            
            tool_calls_from_gemini = []
            candidates = getattr(response, "candidates", None)
            parts = None
            if candidates and getattr(candidates[0], "content", None):
                parts = getattr(candidates[0].content, "parts", None)
                if parts:
                    tool_calls_from_gemini = [
                        part.function_call for part in parts if getattr(part, "function_call", None)
                    ]

            # If the LLM wants to call a tool, execute it
            if tool_calls_from_gemini and parts:
                gemini_messages.append({"role": "model", "parts": parts})
                results = self.handle_tool_calls(tool_calls_from_gemini)
                gemini_messages.extend(results)
            else:
                done = True

        # Return the text content from the final model response.
        final_text_parts = []
        if candidates and getattr(candidates[0], "content", None):
            parts = getattr(candidates[0].content, "parts", None)
            if parts:
                final_text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", None)]
        return final_text_parts[0] if final_text_parts else "" 


if __name__ == "__main__":
    me = Me()
    gr.ChatInterface(me.chat, type="messages").launch()