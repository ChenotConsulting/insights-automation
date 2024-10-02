from fastapi import FastAPI, Response, Header, status
from typing import Union
from typing_extensions import Annotated
import uvicorn
import os
from dotenv import load_dotenv
from main import Main
import logging
import traceback
from pydantic import BaseModel

class Insights(BaseModel):
  userId: str
  days: int = 1

class Post(BaseModel):
  userId: str
  days: int = 2
  insightIds: list = [] # TODO: Replace array with text and split items by comma
  role: str = 'You are a marketing manager working for a consultancy called ProfessionalPulse.'
  post_prompt: str = ''
  image_prompt: str = f'Generate an image based on the following LinkedIn post:'

load_dotenv()
app = FastAPI()

def authoriseRequest(x_api_key):
   auth_api_key = os.getenv('AUTH_API_KEY')
   if auth_api_key == x_api_key:
      return True
   else:
      return False

@app.post("/marketing/feedly/insights", status_code=status.HTTP_200_OK)
def generateFeedlyInsights(insights: Insights, response: Response, x_api_key: Annotated[Union[str, None], Header()] = None):
  try: 
    if authoriseRequest(x_api_key):
      main = Main()
      insights = main.generateInsights(userId=insights.userId, days=insights.days)
      results = None

      if insights == "no-articles-found":
        results = {
          "status": "No articles found"
        }
        response.status_code = status.HTTP_404_NOT_FOUND
      if insights == "no-config-found":
        results = {
          "status": "User config not found"
        }
        response.status_code = status.HTTP_404_NOT_FOUND
      if insights == "insights-failed":
        results = {
          "status": "Could not insert insights in the database"
        }
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
      else:
        results = {
          "status": "OK",
          "results": {
            "insights": insights[0] if insights is not None else "No insights.",
            "urls": insights[1] if insights is not None else "No URLs."
          }
        }          

      return results
    else:
      results = {
        "status": "Not Authorized",
        "message": "You are not authorized to access this service."
      }
      response.status_code = status.HTTP_401_UNAUTHORIZED
      return results
  except Exception as e:
    error = {
      "status": "Error", 
      "message": f"Error generating insights: {e}",
      "traceback": traceback.print_exc()
    }
    logging.error(error)
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return error

@app.post("/marketing/feedly/insights/linkedinpost", status_code=status.HTTP_200_OK)
def generateFeedlyInsightsLinkedInPost(post: Post, response: Response, x_api_key: Annotated[Union[str, None], Header()] = None):
  logging.info(post)
  try: 
    if authoriseRequest(x_api_key):
      main = Main()
      post = main.generateLinkedInPost(userId=post.userId, days=post.days, insightIds=post.insightIds, prompt_role=post.role, post_prompt=post.post_prompt, image_prompt=post.image_prompt)

      if post == "no-articles-found":
        results = {
          "status": "No articles found"
        }
        response.status_code = status.HTTP_404_NOT_FOUND
      if post == "no-config-found":
        results = {
          "status": "User config not found"
        }
        response.status_code = status.HTTP_404_NOT_FOUND
      if post == "post-failed":
        results = {
          "status": "The post could not be saved to the database"
        }
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
      else:
        results = {
          "status": "OK",
          "results": {
            "post": post[0],
            "urls": post[1],
            "image": post[2]
          }
        }

      return results
    else:
      results = {
        "status": "Not Authorized",
        "message": "You are not authorized to access this service."
      }
      response.status_code = status.HTTP_401_UNAUTHORIZED
      return results
  except Exception as e:
    error = {
      "status": "Error", 
      "message": f"Error generating LinkedIn post: {e}"
    }
    logging.error(error)
    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return error

@app.get("/marketing/health", status_code=status.HTTP_200_OK)
def checkHealth():
  result = {
    "status": "OK"
  }
  logging.info(result)
  return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Starting webserver...")

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8080)),
            log_level=os.getenv('LOG_LEVEL', "info"),
            proxy_headers=True
        )
    except Exception as e:
        error = {
           "status": "error",
           "message": f"Error launching application: {e}"
        }
        logging.error(error)

    # generateFeedlyInsights(userId='1699685958170x317202834451805900', days=3)