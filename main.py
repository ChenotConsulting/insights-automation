import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
# from newspaper import Article
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
import openai
import smtplib
import tiktoken
import sys
import logging
import re
from database.mongodb import MongoDB

class Main():
  def __init__(self):
    logging.basicConfig(level=logging.INFO)

    self.MONGODB_USERID = os.getenv('MONGODB_USERID')
    self.FEEDLY_API_URL = os.getenv('FEEDLY_API_URL', 'https://cloud.feedly.com')
    self.INOREADER_API_URL = os.getenv('INOREADER_API_URL', 'https://www.inoreader.com/reader/api/0')
    self.MODEL = 'chatgpt-4o-latest'
    self.MAX_TOKENS = 128000

  def getLocalConfig(self, setupClients):
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

    if self.FEEDLY_ACCESS_TOKEN is not None and setupClients:
      self.setupClients()

  def getConfig(self, userId):
    logging.info(f'Get config for user {userId}')
    self.mongo = MongoDB()
    config = self.mongo.findConfigForUser(userId=userId)
    if config is not None:
      self.FEEDLY_USER_ID = config['feedly']['user']
      self.FEEDLY_ACCESS_TOKEN = config['feedly']['accessToken']
      self.FEEDLY_FOLDERS_LIST = str(config['feedly']['folders']).split(', ')

      self.INOREADER_APP_ID = str(config['inoreader']['appId'])
      self.INOREADER_APP_KEY = str(config['inoreader']['appKey'])
      self.INOREADER_ACCESS_TOKEN = str(config['inoreader']['accessToken'])
      self.INOREADER_FOLDERS_LIST = str(config['inoreader']['folders']).split(', ')
      
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

    self.inoreader = requests.Session()
    self.inoreader.headers = {
      'AppId': self.INOREADER_APP_ID,
      'AppKey': self.INOREADER_APP_KEY,
      'Authorization': f'GoogleLogin auth= {self.inoReaderClientLogin()}'
    }

    openai.api_key = self.OPENAI_API_KEY

  def inoReaderClientLogin(self):
    inoreader = requests.Session()
    inoreader.headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    data = {
      'Email': os.getenv('INOREADER_CLIENT_EMAIL'),
      'Passwd': os.getenv('INOREADER_CLIENT_PWD')
    }
    
    auth_request = inoreader.post(url="https://www.inoreader.com/accounts/ClientLogin", data=data)
    self.INOREADER_AUTH_CODE = re.search(r'Auth=([^;]+)', auth_request.text)[1].strip()
    return self.INOREADER_AUTH_CODE
  
  def count_tokens(self, text):
      enc = tiktoken.get_encoding("cl100k_base")
      token_count = enc.encode(text)
      
      return len(token_count)

  def callOpenAIChat(self, role, prompt):
    logging.info('Connecting to ChatGPT to generate content...')
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
    logging.info('Connecting to ChatGPT to generate an image...')
    response = openai.Image.create(
      model="dall-e-3",
      prompt=prompt,
      size="1024x1024",
      quality="standard",
      n=1,
    )

    return response.data[0].url

  def generateFeedlyInsights(self, days, userId):
    """
    Generate insights from the articles
    """
    if self.getConfig(userId):
      for folder_id in self.FEEDLY_FOLDERS_LIST:
        articles = self.getFeedlyArticles(folder_id=folder_id, daysdelta=days)

        if articles:
          logging.info(f'Generating insights from articles in Feedly folder: {folder_id}')
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
    
  def generateInoreaderInsights(self, numarticles, userId):
    if self.getConfig(userId):
      for folder_id in self.INOREADER_FOLDERS_LIST:
        articles = self.getInoreaderArticles(folder_id, numarticles)

        if articles:
          if articles:
            logging.info(f'Generating insights from articles in Inoreader folder: {folder_id}')
            article_prompts = [f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n' for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents)]
            
            role = 'You are a board avisor specialising in AI sustainability.'
            prompt = f'Extract the key insights & trends, as well as a summary of each article, in UK English from these {self.article_count} articles by accessing the articles from the URLs. For each key insight, list the source article including the title and the URL:\n'
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

  def emailFeedlyInsights(self):
    """
    Generate insights from the Feedly articles
    """
    for folder_id in self.FEEDLY_FOLDERS_LIST:
      articles = self.getFeedlyArticles(folder_id=folder_id, daysdelta=1)

      if articles:
        logging.info(f'Generating insights from articles in Feedly folder: {folder_id}')
        article_prompts = [f'URL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n' for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents)]
        
        role = 'You are a research analyst writing in UK English.'
        prompt = f'Extract the key insights & trends from these {self.article_count} articles and highlight any resources worth checking. For each key insight, mention the source article:\n'
        for article_prompt in article_prompts:
          prompt += article_prompt

        insights = self.callOpenAIChat(role, prompt)

      self.sendEmail(subject=f'Feedly Insights from {self.article_count} articles for folder {folder_id}', body=insights, urls=self.urls)

  def emailInoreaderInsights(self):
    """
    Generate insights from the Inoreader articles
    """
    if self.getConfig(self.MONGODB_USERID):
      for folder_id in self.INOREADER_FOLDERS_LIST:
        articles = self.getInoreaderArticles(folder_id=folder_id, numarticles=3)

        if articles:
          logging.info(f'Generating insights from articles in Inoreader folder: {folder_id}')
          article_prompts = [f'URL: {url}\nTitle: {title}\nSummary: {summary}\Content: {content}\n' for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents)]
          
          role = 'You are a board avisor specialising in AI sustainability.'
          prompt = f'Extract the key insights & trends, as well as a summary of each article, in UK English from these {self.article_count} articles. For each key insight, list the source article including the title and the URL:\n'
          for article_prompt in article_prompts:
            prompt += article_prompt

          insights = self.callOpenAIChat(role, prompt)

        self.sendEmail(subject=f'Inoreader Insights from {self.article_count} articles for folder {folder_id}', body=insights, urls=self.urls)
    else:
      return 'Could not load configuration from MongoDB'
  
  def generateLinkedInPostFromInoreader(self, userId, numarticles, insightIds, prompt_role, post_prompt, image_prompt):
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
              prompt = f'\nContext: My mission is to guide startups in the AI and sustainability space to build products that have a positive impact on the planet and the environment.'
              prompt += f'As a board advisor I want to make sure that every decision made considers the UN sustainable development goals and the impact our actions have.'
              prompt += f'\nThe post must be written from the voice of the board advisor.'
              prompt += f'\nDo not use the context in the post. It\'s for your information only.'
              prompt += f'\nYou should only talk about the insights and trends extracted from these articles with a bias towards process automation.'
              prompt += f'\nWord the insights as if I was commenting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
              prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and sustainability, and sound professional but not formal.'
              prompt += f'\nMention that the links are in the first comment.'
              prompt += f'\nFinish with a call to action asking readers to comment on my posts.'
              prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3, as well as some hashtags related to the insights.'
              prompt += f'\nYou are tasked with generating a LinkedIn post including the links to the relevant articles from these insights: {insights}, generated from these URLs: {urls}'
      else:
        articles = self.getInoreaderArticles(folder_id=self.INOREADER_FOLDERS_LIST[0], numarticles=numarticles)
        if articles:
          logging.info(f'Generating LinkedIn post from Inoreader articles in folder: {self.INOREADER_FOLDERS_LIST[0]}')
          urls = self.urls
          role = prompt_role

          if post_prompt != '':
              prompt = post_prompt
              for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents):
                prompt += f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n'
          else:
            prompt = f'\nContext: My mission is to guide startups in the AI and sustainability space to build products that have a positive impact on the planet and the environment.'
            prompt += f'As a board advisor I want to make sure that every decision made considers the UN sustainable development goals and the impact our actions have.'
            prompt += f'\nThe post must be written from the voice of the board advisor.'
            prompt += f'\nDo not use the context in the post. It\'s for your information only.'
            prompt += f'\nYou should only talk about the insights and trends extracted from these articles with a bias towards process automation.'
            prompt += f'\nWord the insights as if I was commenting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
            prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and sustainability, and sound professional but not formal.'
            prompt += f'\nMention that the links are in the first comment.'
            prompt += f'\nFinish with a call to action asking readers to comment on my posts.'
            prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3, as well as some hashtags related to the insights.'          
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

  def emailFeedlyLinkedInPost(self):
    """
    Generate a LinkedIn post from the articles
    """
    for folder_id in self.FEEDLY_FOLDERS_LIST:
      articles = self.getFeedlyArticles(folder_id=folder_id, daysdelta=2)

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

  def emailInoreaderLinkedInPost(self):
    """
    Generate a LinkedIn post from the articles
    """
    self.getConfig(self.MONGODB_USERID)

    for folder_id in self.INOREADER_FOLDERS_LIST:
      articles = self.getInoreaderArticles(folder_id=folder_id, numarticles=3)

      if articles:
        logging.info(f'Generating LinkedIn post from Inoreader articles in folder: {folder_id}')
        role = 'You are a board advisor operating as Chenot Consulting Ltd.'
        prompt = f'\nContext: My mission is to guide startups in the AI and sustainability space to build products that have a positive impact on the planet and the environment.'
        prompt += f'As a board advisor I want to make sure that every decision made considers the UN sustainable development goals and the impact our actions have.'
        prompt += f'\nThe post must be written from the voice of the board advisor.'
        prompt += f'\nDo not use the context in the post. It\'s for your information only.'
        prompt += f'\nYou should only talk about the insights and trends extracted from these articles with a bias towards process automation.'
        prompt += f'\nWord the insights as if I was commenting on the article rather than just writing an extract. Each insight must be a short paragraph rather than a single sentence.'
        prompt += f'\nThe post must be written in UK English, focused on the key insights around AI and sustainability, and sound professional but not formal.'
        prompt += f'\nMention that the links are in the first comment.'
        prompt += f'\nFinish with a call to action asking readers to comment on my posts.'
        prompt += f'\nAll posts must include this at the bottom: Image source: DALL-E 3, as well as some hashtags related to the insights.'          
        prompt += f'\nYou are tasked with extracting insights and generating a LinkedIn post without icons, including the links to the relevant articles from these {self.article_count} articles:'
        for url, title, summary, content in zip(self.urls, self.titles, self.summaries, self.contents):
          prompt += f'\nURL: {url}\nTitle: {title}\nSummary: {summary}\nContent: {content}\n'

        post = self.callOpenAIChat(role, prompt)
        image = self.callOpenAIImage(f'Generate an image based on the following LinkedIn post. The image must have no text on it: \n{post}')
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

  def getFeedlyArticles(self, folder_id, daysdelta):
    # Get articles from last 24 hours
    timeframe = datetime.now() - timedelta(days=daysdelta)
    timestamp_ms = int(timeframe.timestamp() * 1000)

    logging.info(f'Getting Feedly articles for folder: {folder_id}')
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
        logging.info(f'There are no Feedly articles to analyse for folder {folder_id}.')
        logging.info('========================================================================================') 
    else:
      logging.warning(f'Could not get Feedly articles with status code: {response.status_code}. Details: \n{response.content}') 

    return False
  
  def getInoreaderArticles(self, folder_id, numarticles = 3):
    logging.info(f'Getting Inoreader articles for folder: {folder_id}')
    # Get articles ids for this folder
    inoreader_url = f'{self.INOREADER_API_URL}/stream/contents/{folder_id}?n={numarticles}'
    logging.info(f'Getting articles with Inoreader URL: {inoreader_url}')
    self.inoreader.headers = {
      'Authorization': f'GoogleLogin auth={self.inoReaderClientLogin()}',
      'AppId': self.INOREADER_APP_ID,
      'AppKey': self.INOREADER_APP_KEY
    }
    response = self.inoreader.get(inoreader_url)
    
    if(response.status_code == 200):
      # logging.info(f'Inoreader response: {json.dumps(json.loads(response.text), indent=4)}')
      articles = json.loads(response.text)['items']
      # logging.info(f'articles: {articles}')
      logging.info(f'Retrieved {len(articles)} articles.')
      self.article_count = len(articles)

      if(self.article_count > 0):
        # Concatenate articles in this folder
        self.urls = [a['canonical'][0]['href'] for a in articles]
        self.titles = [a['title'] for a in articles]
        self.summaries = [a['summary']['content'] if 'summary' in a else '' for a in articles]
        self.contents = [self.extractArticleContent(a['canonical'][0]['href']) for a in articles]

        return True
      else: 
        logging.info('========================================================================================')
        logging.info(f'There are no articles to analyse for Inoreader folder {folder_id}.')
        logging.info('========================================================================================') 
    else:
      logging.warning(f'Could not get Inoreader articles with status code: {response.status_code}. Details: \n{response.content}') 

    return False
  
  def extractArticleContent(self, url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)

    if re.search(r'consent.google.com([^;]+)', driver.current_url):
      driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Accept all')]").click()

    time.sleep(2)
    final_url = driver.current_url
    driver.quit()

    article = requests.get(final_url)
    element = ''
    content = ''

    if article.status_code == 200:
    # BEAUTIFUL SOUP METHOD
      soup = BeautifulSoup(article.text, 'html.parser')
      content = soup.get_text()

    #   element = soup.find(class_=re.search(r'content([^;]+)'))
    #   if element is not None:
    #     content = element.get_text()
    #   elif soup.find(class_ = re.compile('article-content')):
    #     element = soup.find(class_ = re.compile('article-content'))
    #     content = element.get_text()
    #   elif soup.find(id_ = re.compile('article_content')):
    #     content = soup.find(if_ = re.compile('article_content'))
    #   elif soup.find(class_ = re.compile('main_content')):
    #     content = soup.find(class_ = re.compile('main_content'))
    #   elif soup.find(class_ = re.compile('article')):
    #     content = soup.find(class_ = re.compile('article'))
    #   elif soup.find(class_ = re.compile('content')):
    #     content = soup.find(class_ = re.compile('content'))
    #   elif soup.find(id_ = re.compile('content')):
    #     content = soup.find(id_ = re.compile('content'))
    #   elif soup.find(class_ = re.compile('post')):
    #     content = soup.find(class_ = re.compile('post'))
    #   elif soup.find(id_ = re.compile('post')):
    #     content = soup.find(id_ = re.compile('post'))
    #   elif soup.find('article'):
    #     content = soup.find('article')      
    #   elif soup.find('main'):
    #     content = soup.find('main')
    #   else:
    #     content = soup.find('body')
    # else: 
    #   return 'article-not-found'
    
    # NEWSPAPER3K SOUP METHOD
    # article = Article(url=final_url, fetch_images=False, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    # article.download()
    # article.parse()
    # content = article.text

    return content.strip()

  def main(self, arg):
    self.args = arg
    logging.info(f'Starting process for option: {self.args}')
    # self.getLocalConfig()

    if self.args == 'Generate Feedly Insights':
      self.emailFeedlyInsights()
    if self.args == 'Create Feedly LinkedIn post':
      self.emailFeedlyLinkedInPost()
    if self.args == 'Generate Inoreader Insights':
      self.emailInoreaderInsights()
    if self.args == 'Create Inoreader LinkedIn post':
      self.emailInoreaderLinkedInPost()
    if self.args == 'Test Inoreader Client Login':
      self.inoReaderClientLogin()
    
if __name__ == "__main__":
  main = Main()

  if len(sys.argv) > 1:
    if sys.argv[1] == '1':
      main.main('Generate Feedly Insights')
    if sys.argv[1] == '2':
      main.main('Create Feedly LinkedIn post')
    if sys.argv[1] == '3':
      main.main('Generate Inoreader Insights')
    if sys.argv[1] == '4':
      main.main('Create Inoreader LinkedIn post')
    if sys.argv[1] == '5':
      main.main('Test Inoreader Client Login')
  else:
    options = ['Generate Feedly Insights', 'Create Feedly LinkedIn post', 'Generate Inoreader Insights', 'Create Inoreader LinkedIn post', 'Test Inoreader Client Login']
    print("Select an option:")
    for index, option in enumerate(options):
        print(f"{index+1}) {option}")

    selection = input("Enter the number of your choice: ")
    if selection.isdigit() and 1 <= int(selection) <= len(options):
        selected_option = options[int(selection) - 1]
    
    main.main(selected_option)