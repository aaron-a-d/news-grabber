# pip install streamlit requests openai beautifulsoup4 orjson

import streamlit as st
from openai import OpenAI
import datetime
from urllib.parse import urlparse
import os
from bs4 import BeautifulSoup
from scrapingbee import ScrapingBeeClient
import orjson

st.set_page_config(layout="wide")

if not os.environ.get('openai') or not os.environ.get('scrapingbee'):
    OPENAI_KEY = st.sidebar.text_input("Enter your OpenAI API key:", type="password")
    SCRAPINGBEE_KEY = st.sidebar.text_input("Enter your ScrapingBee API key:", type="password")
else:
    OPENAI_KEY = os.environ['openai']
    SCRAPINGBEE_KEY = os.environ['scrapingbee']

prompts = {
    "translate": """
        Translate this text into english.
        TEXT:
        {text}
    
        YOUR TRANSLATION:
        """,
    "title": """
        Act as a journalist with 20 years of experience. Summarize the text between the tags `text` in a news-like punch-line in English. Put emphasis on the text's main argument and the identities involved. Omit period or full stop at the end of the result.
        <text>{text}</text>
        YOUR RESPONSE:
        """,
    "summary": """
        Act as a journalist with 20 years of experience. Summarize the text between the tags `text` in 150 words or less in English. Put emphasis on the main argument and the names of people and entities involved. Include one single quote from the text best supporting the main argument.
        <text>{text}</text>
        YOUR RESPONSE:
        """,
    "what": """
        Analyze the text between the tags `text` and return a JSON in English titled "what", containing an array of all the arguments advanced in the text to support the main claim of the text. Put each argument in an object with the following keys: 
        "arg" : containing the argument in a keyword,
        "desc" : a punchline summary of text supporting the argument. 
        <text>{text}</text>
        JSON:
        """,
    "where": """
        Analyze the text between the tags `text` and return a JSON in English titled "where", containing an array of all the geographical locations mentioned in the text ordered in the following way:
        region : english name of the world-region where the geographical location is located at,
        country : english name of the country where the geographical location is located at,
        city : english name of the city where the geographical location is located at,
        orig : the name of the geographical location copied from the text
        name : the english name of the geographical location or a transcription of the name in latin alphabet,
        desc : a punchline describing the geographical location mentioned in the text.
        <text>{text}</text>
        JSON:
        """,
    "who": """
        Analyze the text between the tags `text` and return a JSON in English titled "who", containing an array of the highest taxonomical refference to all individual-humans or individual-entities or individual-objects mentioned in the text ordered in the following way:
        orig : the name of the human or entity or object copied from the text
        name : the name of the human or entity or object in english or a transcription of the name in latin alphabet,
        desc : a punchline describing the the human or entity or object copied from the text.
        <text>{text}</text>
        JSON:
        """,
    "extract_content": """
        Act as a journalist with 20 years of experience. You will receive the HTML code of an article between the tag `html`. I want you to return a JSON with the following keys:
        - title: the title of the article in the original language.
        - time: time of the publication, formatted yyyy-mm-dd hh:mm.
        - content: article itself in the original language.
        - title_en: the title translated in english.
        - content_en: the article translated in english.
        - summary: Summarize the article in 150 words or less in English. Put emphasis on the main argument and the names of people and entities involved. Include one single quote from the text best supporting the main argument. 
        
        
        <html>
        {text}
        </html>
        
        JSON:
        """
}

if OPENAI_KEY and SCRAPINGBEE_KEY:
    client_scrap = ScrapingBeeClient(api_key=SCRAPINGBEE_KEY)
    client_openai = OpenAI(api_key=OPENAI_KEY)

    @st.cache_data(ttl=3600*24)
    def scrape(target_url):
        response = client_scrap.get(target_url)
        return response.text


    def clean_html(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        if soup.head:
            soup.head.decompose()
        for script in soup.find_all('script'):
            script.decompose()
        return str(soup)


    @st.cache_data(ttl=3600*24)
    def ask_gpt(prompt, json=False):
        response = client_openai.chat.completions.create(
            model="gpt-4o",  # gpt-4o | gpt-3.5-turbo-0125
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"} if json else None,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        r = response.choices[0].message.content
        if json:
            r = orjson.loads(r)
        return r


    def extract_meta_properties(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        properties = {}
        for tag in soup.find_all('meta'):
            property_name = tag.get('property')
            content = tag.get('content')
            if property_name and content:
                properties[property_name] = content
        return properties


    def get_article_details_kan(html):
        soup = BeautifulSoup(html, 'html.parser')
        content = soup.find('div', class_='article-section')
        return content

    def display_open_graph_metadata(metadata):
        if metadata:
            st.markdown(f"#### {metadata.get('og:title', '')}")
            st.image(metadata.get('og:image', ''), caption=metadata.get('og:description', ''), width=600)
            st.markdown(f"{metadata.get('og:description', '')}")
            st.markdown(f"{metadata.get('og:url', '')}")
            if metadata.get('article:published_time'):
                st.markdown(f"**Published Time:** {metadata.get('article:published_time')}")
        else:
            st.write("No Open Graph Data.")

    article_url = st.text_input("Enter the article link:")

    if len(article_url) > 0:
        html_text = scrape(article_url)
        html_article = get_article_details_kan(html_text)
        article_json = ask_gpt(prompts['extract_content'].format(text=html_article), json=True)
        metadata_properties = extract_meta_properties(html_text)
        metadata_properties['og:title'] = ask_gpt(prompts["translate"].format(text=metadata_properties['og:title']))
        metadata_properties['og:description'] = ask_gpt(prompts["translate"].format(text=metadata_properties['og:description']))

        what = ask_gpt(prompts['what'].format(text=article_json['content_en']), json=True)
        where = ask_gpt(prompts['where'].format(text=article_json['content_en']), json=True)
        who = ask_gpt(prompts['who'].format(text=article_json['content_en']), json=True)


        col1, _, col2 = st.columns([2, 0.3, 2])

        # Left Column
        with col1:
            st.subheader("Social Media Snippet")
            display_open_graph_metadata(metadata_properties)
            st.divider()

            col1.subheader("AI Analysis")
            col1.markdown(f"#### {article_json['title_en']}")
            col1.write(article_json['summary'])
            st.divider()

            st.subheader("What")
            for e in what['what']:
                st.write(f"- **{e['arg']}**: {e['desc']}")

            st.subheader("Where")
            for e in where['where']:
                st.write(f"- **{e['country']}, {e['city']}, {e['name']}**: {e['desc']}")

            st.subheader("Who")
            for e in who['who']:
                st.write(f"- **{e['name']}**: {e['desc']}")
            st.divider()

        # Right Column
        with col2:
            st.subheader("Translation")
            st.markdown(f"#### {article_json['title_en']}")
            st.caption(f"{article_json['time']}")
            st.write(f"{article_json['content_en']}")
            st.divider()

            st.subheader("Source")
            st.markdown(f"#### {article_json['title']}")
            st.caption(f"{article_json['time']}")
            st.write(f"{article_json['content']}")
            st.divider()

        # with st.expander("What / Where / Who JSONs"):
        #     st.json(what)
        #     st.json(where)
        #     st.json(who)
