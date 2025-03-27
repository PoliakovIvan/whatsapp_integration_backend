import logging
from fastapi import FastAPI
from pydantic import BaseModel
import requests
import os
import uvicorn
import json
from datetime import datetime, timezone
import uuid
from dotenv import load_dotenv

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

class ContactData(BaseModel):
    chatType: str
    chatId: str
    source: str

class CreateContactCollection(BaseModel):
    responsibleUserId: str
    name: str
    contactDataArray: list[ContactData]

class WebhookData(BaseModel):
    createContactCollection: CreateContactCollection

@app.post("/webhook")
async def webhook_handler(payload: WebhookData):
    data = payload.model_dump()
    event_id = uuid.uuid4()
    webhook_logger.info(f"ID:{event_id} | Received webhook data: {json.dumps(data)}") # Logging of input data
    action_logger.info(f"------ ID:{event_id} ------") 
    error_logger.error(f"------ ID:{event_id} ------")

    phone = data['createContactCollection']['contactDataArray'][0]['chatId']
    name = data['createContactCollection']['name']
    HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY"),
    URL = 'https://api.hubapi.com/crm/'

    headers = {
            "Authorization": f"Bearer {HUBSPOT_API_KEY}",
            "Content-Type": "application/json"
        }
    
    contact_data = search_contact(URL, headers, phone)
    
    # If the contact does not exist
    if contact_data['total'] == 0:

        # create new contact 
        new_contact = create_contact(URL, headers, name, phone) 
        action_logger.info(f"Created new contact {name} {phone}") 

        # get the contact's ID to create a new deal |  creating a note about a new message in WhatsApp
        contact_id = new_contact['id']
        create_hubspot_note(contact_id, URL, headers) 
        action_logger.info(f"Created new note for {name} with ID {contact_id}") 

        # creating a deal for a contact in Pipeline 'B2B Wazzup Deal'
        create_deal(URL, headers, name, contact_id) 
        action_logger.info(f"Created new deal for {name} with ID {contact_id}") 

    # If the contact exist
    else: 
        # get contact id | create new note about a new message in WhatsApp
        contact_id = contact_data['results'][0]['id']
        create_hubspot_note(contact_id, URL, headers)
        action_logger.info(f"Created new note for {name} with ID {contact_id}") 

    return {"status": "success"}

#-------------------------------------
#      SEARCH CONTACT IN HUBSPOT
#-------------------------------------  
def search_contact(URL, headers, phone):
    url = f"{URL}v3/objects/contacts/search"
    
    data = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "phone",
                "operator": "CONTAINS_TOKEN",
                "value": phone
            }]
        }]
    }
    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        error_logger.error(f"Error searching contact for phone {phone}: {response.text}")

    return response.json()

#-------------------------------------
#      CREATE CONTACT IN HUBSPOT
#-------------------------------------  
def create_contact(URL, headers, name, phone):
    url = f"{URL}v3/objects/contacts"

    data = {
        "properties": {
            "firstname": name.split(" ")[0], 
            "lastname": name.split(" ")[1] if len(name.split(" ")) > 1 else "",  
            "phone": phone
        }
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 201:
        return response.json()  
    else:
        error_logger.error(f"Failed to create contact: {response.text}")
        return {"error": "Failed to create contact"}

#-------------------------------------
#      CREATE NOTES IN HUBSPOT
#-------------------------------------  
def create_hubspot_note(contact_id: str, URL, headers):

    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

    data = {
        "properties": {
            "hs_note_body": 'New message in WhatsApp',
            "hs_timestamp": timestamp 
        },
        "associations": [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]
            }
        ]
    }

    response = requests.post(f'{URL}/v3/objects/notes', json=data, headers=headers)

    if response.status_code == 201:
        return response.json()
    else:
        error_logger.error(f"Error creating note for contact {contact_id}: {response.text}")
        return None

#-------------------------------------
#      CREATE DEAL IN HUBSPOT
#-------------------------------------  
def create_deal(URL, headers, name, contact_id):

    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

    data = {
        "properties": {
            "dealname": f'Quick deal - {name}',
            "dealstage": '163836210',  
            "closedate": timestamp
        }
    }
    if contact_id:
        data["associations"] = [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}]
            }
        ]

    response = requests.post(f'{URL}/v3/objects/deals', json=data, headers=headers)

    if response.status_code == 201:
        return response.json()
    else:
        error_logger.error(f"Error creating deal for contact {contact_id}: {response.text}")
        return None   

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

