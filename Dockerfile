# Gunakan image python
FROM python:3.10-slim

# Set direktori kerja
WORKDIR /app

# Copy semua file ke container
COPY . /app

# Install dependensi
RUN pip install -r requirements.txt

# Expose port 7860 (port default Hugging Face)
EXPOSE 7860

# Jalankan Flask
CMD ["python", "app.py"]
