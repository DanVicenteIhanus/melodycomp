# Phase 1: Use the official Python slim image as a base
# Using a 'slim' image keeps the final image size smaller.
FROM python:3.11-slim

# Phase 2: Set the working directory inside the container
WORKDIR /app

# Phase 3: Copy only the requirements file first
# This leverages Docker's layer caching. If the requirements don't change,
# Docker won't reinstall the packages on every build, saving a lot of time.
COPY requirements.txt .

# Phase 4: Install the Python dependencies
# --no-cache-dir reduces the image size by not storing the pip cache.
RUN pip install --no-cache-dir -r requirements.txt

# Phase 5: Copy the rest of your application code
# This includes your 'src/' directory, 'app.py', 'data/', etc.
COPY . .

# Phase 6: Expose the port Streamlit runs on
EXPOSE 8501

# Phase 7: Define the command to run your application
# This command starts the Streamlit server. The flags ensure it's
# accessible from outside the container.
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]# Phase 1: Use the official Python slim image as a base
# Using a 'slim' image keeps the final image size smaller.
FROM python:3.11-slim

# Phase 2: Set the working directory inside the container
WORKDIR /app

# Phase 3: Copy only the requirements file first
# This leverages Docker's layer caching. If the requirements don't change,
# Docker won't reinstall the packages on every build, saving a lot of time.
COPY requirements.txt .

# Phase 4: Install the Python dependencies
# --no-cache-dir reduces the image size by not storing the pip cache.
RUN pip install --no-cache-dir -r requirements.txt

# Phase 5: Copy the rest of your application code
# This includes your 'src/' directory, 'app.py', 'data/', etc.
COPY . .

# Phase 6: Expose the port Streamlit runs on
EXPOSE 8501

# Phase 7: Define the command to run your application
# This command starts the Streamlit server. The flags ensure it's
# accessible from outside the container.
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]