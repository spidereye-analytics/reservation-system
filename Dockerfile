# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /reservation_system

# Copy the current directory contents into the container at /reservation_system
COPY . /reservation_system
COPY ./requirements.txt ./reservation_system/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r ./reservation_system/requirements.txt


# Set the Python path to the reservation_system directory
ENV PYTHONPATH=/reservation_system

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run the FastAPI app using Uvicorn
CMD ["uvicorn", "reservation_system.main:app", "--host", "0.0.0.0", "--port", "8000"]
