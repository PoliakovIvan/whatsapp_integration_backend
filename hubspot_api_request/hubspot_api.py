import logging
from fastapi import FastAPI
from pydantic import BaseModel, EmailStr
import os
import uvicorn
import json
import uuid
import asyncpg
from dotenv import load_dotenv
import requests


# Logging settings
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Logging for webhooks
webhook_logger = logging.getLogger("webhook")
webhook_logger.setLevel(logging.INFO)
webhook_handler = logging.FileHandler(os.path.join(log_directory, "webhook_data.log"))
webhook_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
webhook_logger.addHandler(webhook_handler)

# Logging for actions
action_logger = logging.getLogger("actions")
action_logger.setLevel(logging.INFO)
action_handler = logging.FileHandler(os.path.join(log_directory, "actions.log"))
action_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
action_logger.addHandler(action_handler)

# Logging for errors
error_logger = logging.getLogger("errors")
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler(os.path.join(log_directory, "errors.log"))
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
error_logger.addHandler(error_handler)

app = FastAPI()
load_dotenv() 

class WebhookData(BaseModel):
    id: str
    type: str

@app.post("/webhook")
async def webhook_handler(payload: WebhookData):
    contactId = payload.id
    type = payload.type
    event_id = uuid.uuid4()
    webhook_logger.info(f"ID:{event_id} | Received webhook data: {json.dumps(payload.model_dump())}")
    action_logger.info(f"------ ID:{event_id} ------") 
    error_logger.error(f"------ ID:{event_id} ------")

    HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
    URL = 'https://api.hubapi.com/crm/'

    headers = {
            "Authorization": f"Bearer {HUBSPOT_API_KEY}",
            "Content-Type": "application/json"
        }
    if type == 'contact':
        contact_info = get_contact(URL, headers, contactId)
        print(contact_info)
        if contact_info == None:
            return {"message": "Wrong contact id"}
    else:
        lead_data = get_lead(URL, headers, contactId)
        if not lead_data["results"]:  
            return {"message": "Wrong lead id"}
            
        contactId = lead_data["results"][0]["id"]
        contact_info = get_contact(URL, headers, contactId)
    return {"contact_info": contact_info}

#-------------------------------------
#      GET CONTACT IN HUBSPOT
#-------------------------------------  
def get_contact(URL, headers, contactId):
    url = f"{URL}v3/objects/contacts/{contactId}?properties=phone"

    response = requests.get(url, headers=headers)

    if not response.text.strip():
        logging.error(f"Empty response received for contact {contactId}")
        return None

    # Check if the status code is 200 (OK)
    if response.status_code != 200:
        logging.error(f"Error getting contact {contactId}: {response.status_code} - {response.text}")
        return None  # Return None if the request was unsuccessful

    # Check if the response content is empty or not in JSON format
    if not response.text.strip():
        logging.error(f"Empty response received for contact {contactId}")
        return None  # Handle empty response gracefully

    # Attempt to parse the response as JSON
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        logging.error(f"Failed to decode JSON for contact {contactId}: {response.text}")
        return None 
 
    return data

#-------------------------------------
#      GET LEAD IN HUBSPOT
#-------------------------------------  
def get_lead(URL, headers, lead_id):
    url = f"{URL}v3/objects/deals/{lead_id}/associations/contacts?properties=dealname,amount,dealstage,hs_lastmodifieddate"

    response = requests.get(url, headers=headers)

    # Check if the status code is 200
    if response.status_code != 200:
        logging.error(f"Error getting contact {lead_id}: {response.status_code} - {response.text}")
        return None  

    # Check if the response content is empty or not in JSON format
    if not response.text.strip():
        logging.error(f"Empty response received for contact {lead_id}")
        return None  

    # Attempt to parse the response as JSON
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        logging.error(f"Failed to decode JSON for contact {lead_id}: {response.text}")
        return None 
    print(data)
    return data


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)