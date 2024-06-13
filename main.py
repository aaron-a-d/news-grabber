# pip install streamlit requests openai beautifulsoup4 orjson

import streamlit as st
import requests
import datetime
from scrapingbee import ScrapingBeeClient
from openai import OpenAI
from bs4 import BeautifulSoup
import orjson
from urllib.parse import urlparse

st.set_page_config(layout="wide")

# User inputs their API keys
OPENAI_KEY = st.text_input("Enter your OpenAI API key:", type="password")
SCRAPINGBEE_KEY = st.text_input("Enter your ScrapingBee API key:", type="password")

if OPENAI_KEY and SCRAPINGBEE_KEY:
    client = OpenAI(api_key=OPENAI_KEY)

    def ask_gpt(p, json=False):
        response = client.chat.completions.create(
            model="gpt-3.5-turbo-0125",
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"} if json else None,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": p},
            ]
        )
        r = response.choices[0].message.content
        return r

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
            st.markdown(f"**Title:** {metadata.get('og:title', '')}")
            st.image(metadata.get('og:image', ''), caption=metadata.get('og:description', ''), width=600)
            st.markdown(f"**Description:** {metadata.get('og:description', '')}")
            st.markdown(f"**URL:** {metadata.get('og:url', '')}")
            st.markdown(f"**Published Time:** {metadata.get('article:published_time', '')}")
        else:
            st.write("No Open Graph Data :(")

    def get_article_details_ltn(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')

        def has_exact_classes(tag, classes):
            return tag.name == 'div' and set(tag.get('class', [])) == set(classes)

        div = soup.find(lambda tag: has_exact_classes(tag, ['whitecon', 'boxTitle', 'boxText']))
        if div:
            title = div.find('h1').text if div.find('h1') else None
            time = div.find('div', class_='time').text if div.find('div', class_='time') else None
            content = div.find('div', class_='text').text if div.find('div', class_='text') else None
            return {
                'title': title,
                'time': time,
                'content': content
            }
        else:
            return None

    def get_article_details_kan(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')

        # Extract title
        title_element = soup.find('h1', class_='article-header-title')
        title = title_element.text.strip() if title_element else None

        # Extract time
        time_element = soup.find('div', class_='date-local')
        if time_element:
            date_utc = time_element['data-date-utc']
            # Parse the date format "13.6.2024 17:44:19"
            datetime_utc = datetime.datetime.strptime(date_utc, '%d.%m.%Y %H:%M:%S')
            formatted_time = datetime_utc.strftime('%Y-%m-%d %H:%M:%S')
        else:
            formatted_time = None

        # Extract content
        content_element = soup.find('div', class_='article-content')
        content = content_element.text.strip() if content_element else None

        return {
            'title': title,
            'time': formatted_time,
            'content': content
        }

    def get_article_details_people(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')

        # Find the div with class "layout rm_txt cf"
        main_div = soup.find('div', class_='layout rm_txt cf')

        if main_div:
            # Extract title from h1 tag
            title = main_div.find('h1').text.strip() if main_div.find('h1') else None

            # Extract time from div with class "col-1-1 fl"
            time_div = main_div.find('div', class_='col-1-1 fl')
            time = time_div.text.strip() if time_div else None

            # Extract content from div with class "rm_txt_con cf"
            content_div = main_div.find('div', class_='rm_txt_con cf')
            content = content_div.text.strip() if content_div else None

            return {
                'title': title,
                'time': time,
                'content': content
            }
        else:
            return None

    def get_article_details_reuters(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')

        # Extracting title
        title = soup.select_one('#main-content > article > div.article__main__33WV2 > div > header > div > div > h1')
        title_text = title.text.strip() if title else None

        # Extracting time
        time = soup.select_one(
            '#main-content > article > div.article__main__33WV2 > div > header > div > div > div > div.info-content__author-date__1Epi_ > time')
        time_text = time.get('datetime') if time else None

        # Extracting content
        content = soup.select_one('#main-content > article > div.article__main__33WV2 > div > div')
        content_text = content.text.strip() if content else None

        return {
            'title': title_text,
            'time': time_text,
            'content': content_text
        }

    def get_main_domain(url):
        parsed_url = urlparse(url)
        main_domain = parsed_url.netloc
        return main_domain

    def extract_meta_properties(html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        meta_tags = soup.find_all('meta')
        properties = {}
        for tag in meta_tags:
            property_name = tag.get('property')
            content = tag.get('content')
            if property_name and content:
                properties[property_name] = content
        return properties

    @st.cache(ttl=3600)
    def run_scrap(link):
        client = ScrapingBeeClient(api_key=SCRAPINGBEE_KEY)

        response = client.get(link)
        html_text = response.text

        properties = extract_meta_properties(html_text)
        cleaned_html = clean_html(html_text)
        print("cleaned_html", cleaned_html)
        if get_main_domain(article_url) == "ec.ltn.com.tw":
            selected_div = get_article_details_ltn(cleaned_html)
        elif get_main_domain(article_url) == "www.kan.org.il":
            selected_div = get_article_details_kan(cleaned_html)
        elif get_main_domain(article_url) == "world.people.com.cn":
            selected_div = get_article_details_people(cleaned_html)
        elif get_main_domain(article_url) == "www.reuters.com":
            selected_div = get_article_details_reuters(cleaned_html)
        else:
            return None

        prompt_title = """
            Act as a journalist with 20 years of experience. Summarize the text between the tags `text` in a news-like punch-line in English. Put emphasis on the text's main argument and the identities involved. Omit period or full stop at the end of the result.

            <text>
            {text}
            </text>

            YOUR RESPONSE:
            """

        prompt_summary = """
            Act as a journalist with 20 years of experience. Summarize the text between the tags `text` in 150 words or less in English. Put emphasis on the main argument and the names of people and entities involved. Include one single quote from the text best supporting the main argument.

            <text>
            {text}
            </text>

            YOUR RESPONSE:
            """

        prompt_what = """
            Analyze the text between the tags `text` and return a JSON in English titled "what", containing an array of all the arguments advanced in the text to support the main claim of the text. Put each argument in an object with the following keys: 
            "arg" : containing the argument in a keyword,
            "desc" : a punchline summary of text supporting the argument. 

            <text>
            {text}
            </text>

            JSON:
            """

        prompt_where = """
            Analyze the text between the tags `text` and return a JSON in English titled "where", containing an array of all the geographical locations mentioned in the text ordered in the following way:
            region : english name of the world-region where the geographical location is located at,
            country : english name of the country where the geographical location is located at,
            city : english name of the city where the geographical location is located at,
            orig : the name of the geographical location copied from the text
            name : the english name of the geographical location or a transcription of the name in latin alphabet,
            desc : a punchline describing the geographical location mentioned in the text.

            <text>
            {text}
            </text>

            JSON:
            """

        prompt_who = """
            Analyze the text between the tags `text` and return a JSON in English titled "who", containing an array of the highest taxonomical refference to all individual-humans or individual-entities or individual-objects mentioned in the text ordered in the following way:
            orig : the name of the human or entity or object copied from the text
            name : the name of the human or entity or object in english or a transcription of the name in latin alphabet,
            desc : a punchline describing the the human or entity or object copied from the text.

            <text>
            {text}
            </text>

            JSON:
            """

        if selected_div:
            content = selected_div['content']
            title = ask_gpt(prompt_title.format(text=content))
            summary = ask_gpt(prompt_summary.format(text=content))
            what = ask_gpt(prompt_what.format(text=content), json=True)
            where = ask_gpt(prompt_where.format(text=content), json=True)
            who = ask_gpt(prompt_who.format(text=content), json=True)

        return {
            "selected_div": selected_div,
            "og_properties": properties,
            "content": content,
            "title": title,
            "summary": summary,
            "what": what,
            "where": where,
            "who": who,
        }

    # Streamlit App
    st.title("Article Analysis")

    st.write("""
    Supported Domains:
    - ec.ltn.com.tw
    - www.kan.org.il
    - world.people.com.cn
    - www.reuters.com
    """)

    # User inputs the article link
    article_url = st.text_input("Enter the article link:")

    if article_url and is_valid_url(article_url):

        scrapped = run_scrap(article_url)

        # Display results in two columns
        col1, _ , col2 = st.columns([2, 0.4, 1.5])

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
            st.write(scrapped['title'])

            st.subheader("Source")
            st.write(f"Title: {scrapped['selected_div']['title']}")
            st.write(f"Time: {scrapped['selected_div']['time']}")
            st.write(f"Content: {scrapped['selected_div']['content']}...")  # Truncated content
    else:
        st.info("Please enter an article link to proceed.")
