import os
from dotenv import load_dotenv
import requests
import json
from datetime import datetime, timedelta
import openai
import smtplib
import tiktoken
import sys
import logging
from database.mongodb import MongoDB

class Main():
  def __init__(self):
    logging.basicConfig(level=logging.DEBUG)

    self.FEEDLY_API_URL = os.getenv('FEEDLY_API_URL', 'https://cloud.feedly.com')
    self.MODEL = 'gpt-4-1106-preview'
    self.MAX_TOKENS = 128000

  def getLocalConfig(self):
    # Load environment variables
    logging.info('Loading environment variables...')
    load_dotenv()
    self.FEEDLY_USER_ID = os.getenv('FEEDLY_USER_ID')
    self.FEEDLY_ACCESS_TOKEN = os.getenv('FEEDLY_ACCESS_TOKEN')
    self.FEEDLY_FOLDERS = os.getenv('FEEDLY_FOLDERS')
    if self.FEEDLY_FOLDERS is not None:
      self.FEEDLY_FOLDERS_LIST = str(self.FEEDLY_FOLDERS).split(',')
    self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    self.EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
    self.EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
    self.EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')

    if(self.FEEDLY_ACCESS_TOKEN is not None):
      self.setupClients()

  def getConfig(self, userId):
    logging.info(f'Get config for user {userId}')
    self.mongo = MongoDB()
    config = self.mongo.findConfigForUser(userId=userId)
    if config is not None:
      self.FEEDLY_USER_ID = config['feedly']['user']
      self.FEEDLY_ACCESS_TOKEN = config['feedly']['accessToken']
      self.FEEDLY_FOLDERS_LIST = str(config['feedly']['folders']).split(', ')
      self.OPENAI_API_KEY = config['openai']['apiKey']
      self.EMAIL_USERNAME = config['google']['emailUsername']
      self.EMAIL_PASSWORD = config['google']['emailPassword']
      self.EMAIL_RECIPIENT = config['google']['emailRecipient']

      self.setupClients()
      return True
    else:
      return False

  def setupClients(self):
    # Setup clients
    logging.info('Setting up the API clients...')
    self.feedly = requests.Session()
    self.feedly.headers = {'authorization': f'OAuth {self.FEEDLY_ACCESS_TOKEN}'}
    openai.api_key = self.OPENAI_API_KEY

  def count_tokens(self, text):
      enc = tiktoken.get_encoding("cl100k_base")
      token_count = enc.encode(text)
      
      return len(token_count)

  def callOpenAIChat(self, role, prompt):
    response = openai.ChatCompletion.create(
      model=self.MODEL, 
      temperature=0.2,
      n=1,
      messages=[
        {'role': 'system', 'content': role}, 
        {'role': 'user', 'content': prompt}
      ]
    )
    return response['choices'][0]['message']['content']

  def callOpenAIImage(self, prompt):
    response = openai.Image.create(
      model="dall-e-3",
      prompt=prompt,
      size="1024x1024",
      quality="standard",
      n=1,
    )

    return response.data[0].url

  def generateInsights(self, days, userId):
    """
    Generate insights from the articles
    """
    if self.getConfig(userId):
      for folder_id in self.FEEDLY_FOLDERS_LIST:
        articles = self.getArticles(folder_id=folder_id, daysdelta=days)

        if articles:
          logging.info(f'Generating insights from articles in folder: {folder_id}')
          article_prompts = [f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n' for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents)]
          
          role = 'You are a research analyst.'
          prompt = f'Extract the key insights & trends in UK English from these {self.article_count} articles and highlight any resources worth checking. For each key insight, mention the source article:\n'
          for article_prompt in article_prompts:
            prompt += article_prompt
          insights = self.callOpenAIChat(role, prompt)

          self.mongo = MongoDB()
          if self.mongo.insertInsights(userId=userId, insights=insights, urls=self.urls):
            return [insights, self.urls]
          else:
            return "insights-failed"
        else:
          return "no-articles-found"
    else: 
      return "no-config-found"

  def emailInsights(self):
    """
    Generate insights from the articles
    """
    for folder_id in self.FEEDLY_FOLDERS_LIST:
      articles = self.getArticles(folder_id=folder_id, daysdelta=1)

      if articles:
        logging.info(f'Generating insights from articles in folder: {folder_id}')
        article_prompts = [f'URL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n' for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents)]
        
        role = 'You are a research analyst writing in UK English.'
        prompt = f'Extract the key insights & trends from these {self.article_count} articles and highlight any resources worth checking. For each key insight, mention the source article:\n'
        for article_prompt in article_prompts:
          prompt += article_prompt

        insights = self.callOpenAIChat(role, prompt)

      self.sendEmail(subject=f'Feedly Insights from {self.article_count} articles for folder {folder_id}', body=insights, urls=self.urls)

  def generateLinkedInPost(self, userId, days, insightIds, prompt_role, post_prompt, image_prompt):
    """
    Generate a LinkedIn post from the articles
    """
    config = self.getConfig(userId=userId)
    if config:
      role = None
      prompt = None
      articles = None
      insights = []
      urls = []
      
      if len(insightIds) > 0:
        for id in insightIds:
          self.mongo = MongoDB()
          insight = self.mongo.findInsightById(id)
          if insight is not None:
            insights.append(insight['insights'])
            urls.append(insight['urls'])

            logging.info(f'Generating LinkedIn post from insights')
            self.urls = insight["urls"]
            role = prompt_role
            if post_prompt != '':
              prompt = f'{post_prompt} \n{insights} \n{urls}'
            else:
              prompt = f'\nContext: My mission is to demystify AI and make it accessible and practical for professional services firms. Through ProfessionalPulse, I aim to deliver bespoke AI data strategies that are not only technically sound but also align with the '
              prompt += f'unique business goals and challenges of each client. We strive to turn AI from a concept into a tangible asset, driving innovation, efficiency, and competitive advantage.'
              prompt += f'\nThe post must be written from the voice of the consultancy.'
              prompt += f'\nDo not use the context in the post. It\'s for your information only.'
              prompt += f'\nYou should only talk about the insights extracted from these articles with a bias towards process automation.'
              prompt += f'\nWord the insights as if I was commenting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
              prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and technology, and sound professional as the target audience are professionals.'
              prompt += f'\nMention that the links are in the first comment.'
              prompt += f'\nFinish with a call to action asking readers to message me on LinkedIn if they are interested in discussing either the insights or how I could help them.'
              prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3, as well as some hashtags related to the insights.'
              prompt += f'\nYou are tasked with generating a LinkedIn post including the links to the relevant articles from these insights: {insights}, generated from these URLs: {urls}'
      else:
        articles = self.getArticles(folder_id=self.FEEDLY_FOLDERS_LIST[0], daysdelta=days)
        if articles:
          logging.info(f'Generating LinkedIn post from articles in folder: {self.FEEDLY_FOLDERS_LIST[0]}')
          urls = self.urls
          role = prompt_role

          if post_prompt != '':
              prompt = post_prompt
              for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents):
                prompt += f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n'
          else:
            prompt = f'\nContext: At ProfessionalPulse, we\'re passionate about leveraging technology to transform the operations of Business Services teams within Professional Services Firms.'
            prompt += f'Our journey began in the dynamic realm of IT and consultancy, and was inspired by real-life challenges faced by these teams.'
            prompt += f'Today, we use our expertise and unique approach to help these teams navigate their challenges, boost efficiency, and strike a balance between their professional and personal lives.'
            prompt += f'Discover more about our ethos, our journey, and how we can help you.'
            prompt += f'\nDo not use the context in the post. It\'s for your information only.'
            prompt += f'\nYou should only talk about the insights extracted from the articles with a bias towards process automation, and the links to the articles should be neatly listed at the very end of the post, after everything else.'
            prompt += f'\nUse numbers for each insight to point to the relevant article URL.'
            prompt += f'\nWord the insights as if I was commeting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
            prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and technology, and sound professional as the target audience are professionals.'
            prompt += f'\nMention that the links are in the first comment and add the links at the bottom, listed by the number of the insight they belong to.'
            prompt += f'\nFinish with a call to action asking readers to message me on LinkedIn if they are interested in discussing either the insights or how I could help them.'
            prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3'          
            prompt += f'\nYou are tasked with extracting insights and generate a LinkedIn post including the links to the relevant articles from these {self.article_count} articles:'
            for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents):
              prompt += f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n'     

      if prompt is not None:
        post = self.callOpenAIChat(role, prompt)
        image = self.callOpenAIImage(f'{image_prompt} {post}')
        if self.mongo.insertPost(userId=userId, insightIds=insightIds, post=post, image=image, urls=urls):
          return [post, urls, image]
        else:
          return "post-failed"
      else:
        return "no-articles-found"
    else: 
      return "no-config-found"

  def emailLinkedInPost(self):
    """
    Generate a LinkedIn post from the articles
    """
    for folder_id in self.FEEDLY_FOLDERS_LIST:
      articles = self.getArticles(folder_id=folder_id, daysdelta=2)

      if articles:
        logging.info(f'Generating LinkedIn post from articles in folder: {folder_id}')
        role = 'You are a marketing manager working for a consultancy called ProfessionalPulse.'
        prompt = f'Imagine that you are a marketing manager for a consultancy called ProfessionalPulse.'
        prompt += f'\nContext: At ProfessionalPulse, we\'re passionate about leveraging technology to transform the operations of Business Services teams within Professional Services Firms.'
        prompt += f'Our journey began in the dynamic realm of IT and consultancy, and was inspired by real-life challenges faced by these teams.'
        prompt += f'Today, we use our expertise and unique approach to help these teams navigate their challenges, boost efficiency, and strike a balance between their professional and personal lives.'
        prompt += f'Discover more about our ethos, our journey, and how we can help you.'
        prompt += f'\nYou are tasked with extracting insights and generate a LinkedIn post including the links to the relevant articles from these {self.article_count} articles:'
        for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents):
          prompt += f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n'
        prompt += f'\nDo not use the context in the post. It\'s for your information only.'
        prompt += f'\nYou should only talk about the insights extracted from these articles with a bias towards process automation, and the links to the articles should be neatly listed at the very end of the post, after everything else.'
        prompt += f'\nUse numbers for each insight to point to the relevant article URL.'
        prompt += f'\nWord the insights as if I was commeting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
        prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and technology, and sound professional as the target audience are professionals.'
        prompt += f'\nMention that the links are in the first comment and add the links at the bottom, listed by the number of the insight they belong to.'
        prompt += f'\nFinish with a call to action asking readers to message me on LinkedIn if they are interested in discussing either the insights or how I could help them.'
        prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3'

        post = self.callOpenAIChat(role, prompt)
        image = self.callOpenAIImage(f'Generate an image based on the following LinkedIn post: \n{post}')
        body = post + f'\n\nImage URL: {image}'
        self.sendEmail(subject=f'LinkedIn post from {self.article_count} articles for folder {folder_id}', body=body, urls=self.urls)

  def sendEmail(self, subject, body, urls):
    """
    Set up SMTP server
    """
    smtp_server = smtplib.SMTP('smtp.gmail.com', 587)
    smtp_server.ehlo()
    smtp_server.starttls()
    smtp_server.login(self.EMAIL_USERNAME, self.EMAIL_PASSWORD) # https://support.google.com/accounts/answer/185833

    # Send email 
    logging.info(f'Sending email...')

    try:
      msg = f'Subject: {subject}\n\n{urls}\n\n{body}'
      smtp_server.sendmail(self.EMAIL_USERNAME, self.EMAIL_RECIPIENT, msg.encode('utf-8'))
      logging.info('Email sent!')
      smtp_server.quit()
    except Exception as e:
      logging.error(f'Error sending email: \n{e}')

  def refreshFeedlyToken(self):
    refresh_token = os.getenv('FEEDLY_REFRESH_TOKEN')
    client_id = 'YOUR_CLIENT_ID'
    client_secret = 'YOUR_CLIENT_SECRET'

    url = 'https://cloud.feedly.com/v3/auth/token'
    params = {
        'refresh_token': refresh_token,
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token'
    }

    response = requests.post(url, data=params)
    access_token = response.json()['access_token']

  def getArticles(self, folder_id, daysdelta):
    # Get articles from last 24 hours
    timeframe = datetime.now() - timedelta(days=daysdelta)
    timestamp_ms = int(timeframe.timestamp() * 1000)

    logging.info(f'Getting articles for folder: {folder_id}')
    # Get articles ids for this folder
    feedly_url = f'{self.FEEDLY_API_URL}/v3/streams/ids?streamId={folder_id}&newerThan={timestamp_ms}&count=20'
    logging.info(f'Getting articles with Feedly URL: {feedly_url}')
    response = self.feedly.get(feedly_url)
    
    if(response.status_code == 200):
      # logging.info(f'Feedly response: {json.dumps(json.loads(response.text), indent=4)}')
      ids = json.loads(response.text)['ids']
      # logging.info(f'IDs: {ids}')
      logging.info(f'Retrieved {len(ids)} articles.')

      # Get articles from the ids
      feedly_entries_url = f'{self.FEEDLY_API_URL}/v3/entries/.mget'
      entries_response = self.feedly.post(feedly_entries_url, None, ids)
      # logging.info(f'Entries response: {json.dumps(json.loads(entries_response.text), indent=4)}')
      articles = json.loads(entries_response.text)
      self.article_count = len(articles)

      if(self.article_count > 0):
        # Concatenate articles this folder
        self.urls = [a['alternate'][0]['href'] for a in articles]
        self.titles = [a['title'] for a in articles]
        self.summaries = [a['summary']['content'] if 'summary' in a else '' for a in articles]
        self.contents = [a['fullContent'] if 'fullContent' in a else '' for a in articles]

        return True
      else: 
        logging.info('========================================================================================')
        logging.info(f'There are no articles to analyse for folder {folder_id}.')
        logging.info('========================================================================================') 
    else:
      logging.warning(f'Could not get articles with status code: {response.status_code}. Details: \n{response.content}') 

    return False

  def main(self, arg):
    self.args = arg
    logging.info(f'Starting process for option: {self.args}')
    self.getLocalConfig()

    if self.args == 'Generate Insights':
      self.emailInsights()
    if self.args == 'Create LinkedIn post':
      self.emailLinkedInPost()
    
if __name__ == "__main__":
  main = Main()

  if len(sys.argv) > 1:
    if sys.argv[1] == '1':
      main.main('Generate Insights')
    if sys.argv[1] == '2':
      main.main('Create LinkedIn post')
  else:
    options = ['Generate Insights', 'Create LinkedIn post']
    print("Select an option:")
    for index, option in enumerate(options):
        print(f"{index+1}) {option}")

    selection = input("Enter the number of your choice: ")
    if selection.isdigit() and 1 <= int(selection) <= len(options):
        selected_option = options[int(selection) - 1]
    
    main.main(selected_option)