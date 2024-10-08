# Overview
This application can be run locally as a script or can be deployed as an API. The required dependencies can be found in the `requirements.txt` file at the root of the repository and can be installed by running `pip install -r requirements.txt`.

The application retrieves the articles from a user-created folder in Feedly and for each article extracts the key insights and trends. An email is sent to the specified recipient with the insights.
It also allows the creation of a LinkedIn post with GPT-4 and an accompanying image generated with DALL-E 3. When running as a local application, both the insights and the LinkedIn post are sent as an email to the specified recipient. When running as an API, the ingishts and the post are saved to your MongoDB Atlas database and returned via the API endpoints.

# Environment Variables

### FEEDLY
#ALWAYS REQUIRED \
FEEDLY_SANDBOX_URL=https://sandbox7.feedly.com \
FEEDLY_API_URL=https://cloud.feedly.com 

#ONLY REQUIRED WHEN RUNNING THE APPLICATION LOCALLY \
FEEDLY_USER_ID=[YOUR FEEDLY USER ID] \
FEEDLY_ACCESS_TOKEN=[YOUR FEEDLY ACCESS TOKEN] #[Feedly Developer Portal](https://developer.feedly.com/v3/developer) \
FEEDLY_REFRESH_TOKEN=[YOUR FEEDLY REFRESH TOKEN] \
FEEDLY_FOLDERS=[YOUR FEEDLY FOLDER IDs]

# INOREADER
INOREADER_API_URL=https://www.inoreader.com/reader/api/0 \
INOREADER_CLIENT_EMAIL=[YOUR INOREADER CUSTOMER ACCOUNT] \
INOREADER_CLIENT_PWD=[YOUR INOREADER CUSTOMER PASSWORD]

### OPENAI - ONLY REQUIRED WHEN RUNNING THE APPLICATION LOCALLY
OPENAI_API_KEY=[YOUR OPENAI API KEY]

### GOOGLE EMAIL - ONLY REQUIRED WHEN RUNNING THE APPLICATION LOCALLY
EMAIL_USERNAME=[YOUR GOOGLE EMAIL ADDRESS] \
EMAIL_PASSWORD=[YOUR GOOGLE APP PASSWORD] \
EMAIL_RECIPIENT=[THE RECIPIENT'S EMAIL ADDRESS] 

### LINKEDIN - NOT CURRENTLY IMPLEMENTED
LINKEDIN_USERNAME=[YOUR LINKEDIN USERNAME] \
LINKEDIN_PASSWORD=[YOUR LINKEDIN PASSWORD] \
LINKEDIN_ACCESS_TOKEN=[YOUR LINKEDIN ACCESS TOKEN] 

### MONGODB - ONLY REQUIRED TO RUN THE APPLICATION AS AN API
MONGODB_USERID=[YOUR MONGODB USER ID] \
MONGODB_URL=[YOUR MONGODB DB DOMAIN] \
MONGODB_USERNAME=[YOUR MONGODB DB USERNAME] \
MONGODB_PASSWORD=[YOUR MONGODB DB PASSWORD] 

### AUTHORIZATION - ALWAYS REQUIRED
AUTH_API_KEY=[YOUR APPLICATION API KEY. MUST BE GENERATED] # This is used to secure access to the API \

# Local application
To run this application locally, you need to add a .env file with the key/value pairs above. You then run the command `python3 main.py`

# API
To run it as an API in a Cloud-based platform, you will need to add the environment variables where relevant and not all are required. Most of them are defined in a `config` collection in your MongoDB Atlas database. You will also need a MongoDB Atlas database, which you can create for free: [Getting Started with MongoDB Atlas](https://www.mongodb.com/docs/atlas/getting-started/).
You then need to run the command `python3 app.py`. This will start a `Uvicorn server` running on port 8080. \
