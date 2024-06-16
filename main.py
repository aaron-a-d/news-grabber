# pip install streamlit requests openai beautifulsoup4 orjson

import streamlit as st
import requests
import time
import os
from datetime import datetime, timedelta
from scrapingbee import ScrapingBeeClient
from openai import OpenAI
from bs4 import BeautifulSoup
import orjson
from streamlit.runtime.scriptrunner import get_script_run_ctx
from urllib.parse import urlparse

st.set_page_config(layout="wide")

openai_key = st.sidebar.text_input("Enter your OpenAI API key:", type="password")
scrapingbee_key = st.sidebar.text_input("Enter your ScrapingBee API key:", type="password")

if openai_key and scrapingbee_key:
    client = OpenAI(api_key=openai_key)


    @st.cache_data(ttl=3600)
    def ask_gpt(prompt, json=False):
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # gpt-3.5-turbo | gpt-4o
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"} if json else None,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        return response.choices[0].message.content


    def is_valid_url(url):
        parsed_url = urlparse(url)
        return all([parsed_url.scheme, parsed_url.netloc])


    def clean_html(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        if soup.head:
            soup.head.decompose()
        for script in soup.find_all('script'):
            script.decompose()
        return str(soup)


    def display_open_graph_metadata(metadata):
        if metadata:
            st.markdown(f"{metadata.get('og:title', '')}")
            st.image(metadata.get('og:image', ''), caption=metadata.get('og:description', ''), width=600)
            st.markdown(f"{metadata.get('og:description', '')}")
            st.markdown(f"**URL:** {metadata.get('og:url', '')}")
            st.markdown(f"**Published Time:** {metadata.get('article:published_time', '')}")
        else:
            st.write("No Open Graph Data :(")


    def extract_article_details(html_text, domain):
        soup = BeautifulSoup(html_text, 'html.parser')

        extractors = {
            "ec.ltn.com.tw": get_article_details_ltn,
            "www.kan.org.il": get_article_details_kan,
            "world.people.com.cn": get_article_details_people,
            "www.reuters.com": get_article_details_reuters,
        }

        if domain in extractors:
            return extractors[domain](soup)
        return None


    def get_article_details_ltn(soup):
        div = soup.find('div', class_=['whitecon', 'boxTitle', 'boxText'])
        return {
            'title': div.find('h1').text if div and div.find('h1') else None,
            'time': div.find('div', class_='time').text if div and div.find('div', class_='time') else None,
            'content': div.find('div', class_='text').text if div and div.find('div', class_='text') else None
        }


    def get_article_details_kan(soup):
        title = soup.find('h1', class_='article-header-title')
        time_element = soup.find('div', class_='date-local')
        formatted_time = None
        if time_element:
            date_utc = time_element['data-date-utc']
            datetime_utc = datetime.strptime(date_utc, '%d.%m.%Y %H:%M:%S')
            formatted_time = datetime_utc.strftime('%Y-%m-%d %H:%M:%S')
        content = soup.find('div', class_='article-content')
        return {
            'title': title.text.strip() if title else None,
            'time': formatted_time,
            'content': content.text.strip() if content else None
        }


    def get_article_details_people(soup):
        main_div = soup.find('div', class_='layout rm_txt cf')
        return {
            'title': main_div.find('h1').text.strip() if main_div and main_div.find('h1') else None,
            'time': main_div.find('div', class_='col-1-1 fl').text.strip() if main_div and main_div.find('div',
                                                                                                         class_='col-1-1 fl') else None,
            'content': main_div.find('div', class_='rm_txt_con cf').text.strip() if main_div and main_div.find('div',
                                                                                                               class_='rm_txt_con cf') else None
        }


    def get_article_details_reuters(soup):
        title = soup.select_one('#main-content > article > div.article__main__33WV2 > div > header > div > div > h1')
        time = soup.select_one(
            '#main-content > article > div.article__main__33WV2 > div > header > div > div > div > div.info-content__author-date__1Epi_ > time')
        content = soup.select_one('#main-content > article > div.article__main__33WV2 > div > div')
        return {
            'title': title.text.strip() if title else None,
            'time': time.get('datetime') if time else None,
            'content': content.text.strip() if content else None
        }


    def extract_meta_properties(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        properties = {}
        for tag in soup.find_all('meta'):
            property_name = tag.get('property')
            content = tag.get('content')
            if property_name and content:
                properties[property_name] = content
        return properties


    @st.cache_data(ttl=3600)
    def run_scrap(link):
        client = ScrapingBeeClient(api_key=scrapingbee_key)
        for i in range(5):
            response = client.get(link)
            html_text = response.text
            print(f"html_text {i}: ", html_text)

            try:
                error = orjson.loads(html_text).get('error', '')
                if "Error with your request" in error:
                    print("RETRY!!")
                    time.sleep(1)  # Optional: to avoid hitting the server too rapidly
                    continue
            except orjson.JSONDecodeError:
                # No error in JSON, proceed
                break

        else:
            st.error("Failed to retrieve the article after multiple attempts.")
            return None

        properties = extract_meta_properties(html_text)
        cleaned_html = clean_html(html_text)
        domain = urlparse(link).netloc
        article_details = extract_article_details(cleaned_html, domain)

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
                """
        }

        if article_details:
            content = article_details['content']
            properties['og:title'] = ask_gpt(prompts["translate"].format(text=properties['og:title']))
            properties['og:description'] = ask_gpt(prompts["translate"].format(text=properties['og:description']))

            article_details['title_en'] = ask_gpt(prompts["translate"].format(text=article_details['title']))
            article_details['content_en'] = ask_gpt(prompts["translate"].format(text=article_details['content']))
            return {
                "selected_div": article_details,
                "og_properties": properties,
                "content": content,
                "title": ask_gpt(prompts["title"].format(text=content)),
                "summary": ask_gpt(prompts["summary"].format(text=content)),
                "what": ask_gpt(prompts["what"].format(text=content), json=True),
                "where": ask_gpt(prompts["where"].format(text=content), json=True),
                "who": ask_gpt(prompts["who"].format(text=content), json=True)
            }
        return None


    # Streamlit App
    st.title("Article Analysis")

    st.write("""
    Supported Domains:
    - ec.ltn.com.tw
    - www.kan.org.il
    - world.people.com.cn
    - www.reuters.com
    """)

    article_url = st.text_input("Enter the article link:")

    if article_url and is_valid_url(article_url):
        scrapped = run_scrap(article_url)

        if scrapped:
            col1, _, col2 = st.columns([2, 0.4, 1.5])

            with col1:
                st.header("No Copyrights")
                st.subheader("Social Media Snippet")
                display_open_graph_metadata(scrapped['og_properties'])

                st.subheader("AI Analysis")
                st.write(f"**{scrapped['title']}**")
                st.write(scrapped['summary'])

                st.subheader("What")
                for e in orjson.loads(scrapped['what'])['what']:
                    st.write(f"- **{e['arg']}**: {e['desc']}")

                st.subheader("Where")
                for e in orjson.loads(scrapped['where'])['where']:
                    st.write(f"- **{e['country']}**: {e['desc']}")

                st.subheader("Who")
                for e in orjson.loads(scrapped['who'])['who']:
                    st.write(f"- **{e['name']}**: {e['desc']}")

            with col2:
                st.header("Copyrighted")
                st.subheader("Translation")
                st.write(f"Title: {scrapped['selected_div']['title_en']}")
                st.write(f"Time: {scrapped['selected_div']['time']}")
                st.write(f"Content: {scrapped['selected_div']['content_en']}")

                st.subheader("Source")
                st.write(f"Title: {scrapped['selected_div']['title']}")
                st.write(f"Time: {scrapped['selected_div']['time']}")
                st.write(f"Content: {scrapped['selected_div']['content']}")
        else:
            st.error("Failed to scrape the article. Please check the URL and try again.")
    else:
        st.info("Please enter a valid article link to proceed.")
