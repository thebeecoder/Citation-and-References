from flask import Flask, request, render_template, send_file
import os
from werkzeug.utils import secure_filename
import docx
from PyPDF2 import PdfReader
from scholarly import scholarly
import re
from collections import Counter
import time
import logging
import spacy

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'document' not in request.files:
        return render_template('index.html', message="No file part")

    file = request.files['document']

    if file.filename == '':
        return render_template('index.html', message="No selected file")

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            processed_file = process_file(filepath)
            return send_file(processed_file, as_attachment=True)
        except Exception as e:
            logging.error(f"Error processing file: {e}")
            return render_template('index.html', message="Error processing the file. Please try again.")

    return render_template('index.html', message="Invalid file type. Only PDF and DOCX allowed.")

def process_file(filepath):
    content = extract_content(filepath)
    citations, references = get_relevant_citations(content)

    if filepath.endswith('.docx'):
        processed_file = add_citations_to_docx(filepath, citations, references)
    else:
        processed_file = filepath  # PDF handling can be implemented similarly

    return processed_file

def extract_content(filepath):
    if filepath.endswith('.pdf'):
        reader = PdfReader(filepath)
        content = ''
        for page in reader.pages:
            content += page.extract_text() or ''
        return content
    elif filepath.endswith('.docx'):
        doc = docx.Document(filepath)
        content = "\n".join([para.text for para in doc.paragraphs])
        return content

# Initialize spaCy for NLP tasks
nlp = spacy.load('en_core_web_sm')

def extract_key_phrases(content):
    # Process the content with spaCy NLP
    doc = nlp(content)

    # Extract noun phrases and filter out short phrases (3-6 words long)
    phrases = [chunk.text for chunk in doc.noun_chunks if 3 <= len(chunk.text.split()) <= 6]

    # Return unique phrases
    return list(set(phrases))

def get_relevant_citations(content):
    key_phrases = extract_key_phrases(content)
    citations = {}
    references = []
    citation_count = 1

    # Search Google Scholar for each key phrase and get the first result
    for phrase in key_phrases:
        search_query = scholarly.search_pubs(phrase)

        # Delay to avoid overwhelming Google Scholar
        time.sleep(1)

        try:
            paper = next(search_query)

            # Extract citation details, checking if they exist
            author = paper.get('author', 'Unknown Author')
            title = paper.get('title', 'Untitled')
            journal = paper.get('journal', 'Unknown Journal')
            volume = paper.get('volume', '')
            number = paper.get('number', '')
            pages = paper.get('pages', '')
            year = paper.get('year', '')

            # Construct the citation in IEEE format
            citation = f"{author}, \"{title},\" {journal}, vol. {volume}, no. {number}, pp. {pages}, {year}."

            # Only add unique citations
            if citation not in citations:
                citations[citation] = citation_count
                references.append(citation)
                citation_count += 1

        except StopIteration:
            logging.info(f"No results found for key phrase: {phrase}")
            continue

    if not references:
        references.append("No relevant citations found.")

    return citations, references

def insert_in_text_citations(content, citations):
    # For each key phrase, insert citation number in brackets [n]
    for phrase, number in citations.items():
        if phrase in content:
            content = content.replace(phrase, f"{phrase} [{number}]")
    return content

def add_citations_to_docx(filepath, citations, references):
    doc = docx.Document(filepath)

    # Extract and update content with in-text citations
    full_text = extract_content(filepath)
    content_with_citations = insert_in_text_citations(full_text, citations)

    # Clear existing content and replace with updated content
    for para in doc.paragraphs:
        para.clear()

    # Add the content with citations
    for line in content_with_citations.split('\n'):
        doc.add_paragraph(line)

    # Add References section at the end
    doc.add_paragraph('References')
    for i, citation in enumerate(references):
        doc.add_paragraph(f"[{i + 1}] {citation}")

    # Save the updated document
    new_filepath = filepath.replace(".docx", "_with_citations.docx")
    doc.save(new_filepath)
    return new_filepath

if __name__ == '__main__':
    app.run(debug=True)
