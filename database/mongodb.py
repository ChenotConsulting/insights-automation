import os
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.collection import ObjectId

class MongoDB():
    load_dotenv()

    def __init__(self):
        logging.basicConfig(level=logging.DEBUG)
        self.uri = f"mongodb+srv://{os.getenv('MONGODB_USERNAME')}:{os.getenv('MONGODB_PASSWORD')}@{os.getenv('MONGODB_URL', 'insightsautomation.to3so7y.mongodb.net')}/?retryWrites=true&w=majority"

        # Create a new client and connect to the server
        self.client = MongoClient(self.uri)

    def testConnection(self):
        # Send a ping to confirm a successful connection
        try:
            self.client.admin.command('ping')
            logging.info("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            logging.error(f'Error pinging MongoDB: {e}')

    def findConfigForUser(self, userId):
        try:
            db = self.client.get_database(name='InsightsAutomation')
            coll = db.get_collection('config')
            config = coll.find_one({"userId": userId})
            logging.info(f'Found config for user {userId}')
            return config
        except Exception as e:
            logging.error(f'Error getting config for user {userId}: \n{e}')
            raise Exception(e)
        
    def findInsightById(self, insightId): 
        try:
            db = self.client.get_database(name='InsightsAutomation')
            coll = db.get_collection('insight')
            insight = coll.find_one({"_id": ObjectId(insightId)})
            logging.info(f'Found insight for ID: {insightId}')
            return insight
        except Exception as e:
            logging.error(f'Error getting insight for ID {insightId}: \n{e}')
            raise Exception(e)

    def insertInsights(self, userId, insights, urls):
        insight_document = {
            "userId": userId,
            "insights": insights,
            "urls": urls,
            "timestamp": int(datetime.now().timestamp())
        }

        try:
            db = self.client.get_database(name='InsightsAutomation')
            coll = db.get_collection('insight')
            coll.insert_one(insight_document)
            logging.info(f'Inserted document in insights collection for user {userId}')
            return True
        except Exception as e:
            logging.error(f'Error inserting insights document for user {userId}: \n{e}')
            raise Exception(e)
        
    def insertPost(self, userId, post, image, insightIds, urls = []):
        insight_document = {
            "userId": userId,
            "insightIds": insightIds,
            "post": post,
            "image": image,
            "urls": urls,
            "timestamp": int(datetime.now().timestamp())
        }

        try:
            db = self.client.get_database(name='InsightsAutomation')
            coll = db.get_collection('linkedin_post')
            coll.insert_one(insight_document)
            logging.info(f'Inserted document in post collection for user {userId} from insights: {insightIds}')
            return True
        except Exception as e:
            logging.error(f'Error inserting post document for user {userId} from insights: {insightIds}: \n{e}')
            raise Exception(e)
        