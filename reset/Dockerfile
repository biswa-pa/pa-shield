FROM python:3.12-alpine
RUN pip install --no-cache-dir bcrypt==4.2.1
COPY app.py /app/app.py
COPY email-banner.png /app/email-banner.png
CMD ["python", "-u", "/app/app.py"]
