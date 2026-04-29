# Kaltum Job Search Assistant

Kaltum Job Search Assistant is a Python command-line tool for searching jobs, tracking applications, generating cover letters, exporting job records, and managing follow-up reminders.

## Features

- Search jobs from RemoteOK and Adzuna
- Track job applications in SQLite
- Update application status
- Generate AI cover letters using Claude
- Export tracked jobs to CSV
- Show follow-up reminders

## Commands

python app.py --help  
python app.py profile  
python app.py add  
python app.py track --list  
python app.py track --update 1 --status applied  
python app.py export  
python app.py followup  
python app.py search --role "Data Analyst" --location "Boston" --limit 5  
python app.py cover --company Google --title "Data Analyst"

## Requirements

pip install -r requirements.txt

## Environment Variables

ANTHROPIC_API_KEY=your_key_here  
ADZUNA_APP_ID=your_adzuna_app_id  
ADZUNA_API_KEY=your_adzuna_api_key