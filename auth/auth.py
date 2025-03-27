import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
import os
import uvicorn
import json
import uuid
import asyncpg
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

class EmailCheckRequest(BaseModel):
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

async def get_db_connection():
    try:
        conn = await asyncpg.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT")
        )
        return conn
    except Exception as e:
        print(f"Error: {e}")
        return None

#----------------------
# CHECK IF USER EXIST 
#----------------------
@app.post("/auth/check_email")
async def webhook_handler(payload: EmailCheckRequest):
    email = payload.email
    event_id = uuid.uuid4()
    webhook_logger.info(f"ID:{event_id} | check email: {json.dumps(email)}") # Logging of input data
    action_logger.info(f"------ ID:{event_id} ------") 
    error_logger.error(f"------ ID:{event_id} ------")

    email = payload.email
    conn = await get_db_connection()
    try:
        user = await conn.fetchrow("SELECT id, email, first_login FROM users WHERE email = $1", email)
        
        if user:
            if user["first_login"]:  
                action_logger.info(f"User first login {email}") 
                raise HTTPException(status_code=400, detail="User must complete first login process.") 
            action_logger.info(f"User is login {email}")   
            return {HTTPException(status_code=200)}
        
        return {HTTPException(status_code=400)}

    except Exception as e:
        error_logger.error(f"Failed to check user")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if conn:
            await conn.close()

#----------------------
#       LOGIN
#----------------------
@app.post("/auth/login")
async def login(request: LoginRequest):
    event_id = uuid.uuid4()
    webhook_logger.info(f"ID:{event_id} | login: {request.model_dump_json()}") # Logging of input data
    action_logger.info(f"------ ID:{event_id} ------") 
    error_logger.error(f"------ ID:{event_id} ------")
    conn = await get_db_connection()

    try:
        user = await conn.fetchrow("SELECT id, email, password, first_login, name FROM users WHERE email = $1", request.email)
        if user:

            # Checking the password
            if user["password"] == request.password:
                action_logger.info(f"Login successful: user_id: {user["id"]}, email: {user["email"]}, name:{user["name"]}")   
                return {"message": "Login successful", "user_id": user["id"], "email": user["email"], "name":user["name"]}
            else:
                error_logger.error(f"Incorrect password")
                raise HTTPException(status_code=400, detail="Incorrect password")
        else:
            error_logger.error(f"User not found")
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        error_logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        await conn.close()

#----------------------
#       ADD PASSWORD
#----------------------
@app.post("/auth/add_password")
async def add_password(request: LoginRequest):
    event_id = uuid.uuid4()
    webhook_logger.info(f"ID:{event_id} | add password: {request.model_dump_json()}") # Logging of input data
    action_logger.info(f"------ ID:{event_id} ------") 
    error_logger.error(f"------ ID:{event_id} ------")
    conn = await get_db_connection()

    try:
        user = await conn.fetchrow("SELECT id, email, password, first_login, name FROM users WHERE email = $1", request.email)
        if user:
            # Checking the password
            await conn.execute("UPDATE users SET password = $1, first_login = $2 WHERE email = $3", request.password, False, request.email)
            action_logger.info(f"Update password for user: {request.email}")
            return {HTTPException(status_code=200)}
    except Exception as e:
        error_logger.error(f"Database error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        await conn.close()
 
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)