# Contract App

A web application for managing contracts, connecting with Google Calendar, and scheduling meetings.

## Deploying to Render

This application is configured for deployment on [Render](https://render.com/).

### Prerequisites

1. Create a Render account at https://render.com/
2. Have your MongoDB connection string ready
3. Configure Google OAuth credentials for production

### Deployment Steps

1. **Create a new Web Service on Render**:
   - Connect your GitHub repository
   - Use the following settings:
     - Name: `contract-app-api` (or your preferred name)
     - Environment: `Python`
     - Build Command: `cd server && pip install -r requirements.txt`
     - Start Command: `cd server && gunicorn -c gunicorn_config.py server.main:app`

2. **Configure Environment Variables**:
   Create the following environment variables in your Render dashboard:
   - `ENVIRONMENT`: `production`
   - `MONGO_URI`: Your MongoDB connection string
   - `GOOGLE_CLIENT_ID`: Your Google OAuth client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth client secret
   - `SECRET_KEY`: A strong random secret key for session encryption
   - `FRONTEND_URL`: URL of your frontend (e.g., `https://your-app.onrender.com`)
   - `SMTP_SERVER`: SMTP server for email notifications
   - `SMTP_PORT`: SMTP port (usually 587)
   - `SMTP_USERNAME`: SMTP username
   - `SMTP_PASSWORD`: SMTP password

3. **Update Google OAuth Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Update the authorized redirect URIs to include your Render deployment URL:
     - `https://your-app.onrender.com/auth/google/callback`
     - `https://your-app.onrender.com/auth/google/calendar/callback`

### Alternative: Deploy using render.yaml

If you prefer to use Infrastructure as Code:

1. Push the `render.yaml` file to your repository
2. Go to the Render Dashboard
3. Click "New" > "Blueprint"
4. Select your repository
5. Render will automatically detect the `render.yaml` file and create the services
6. You'll still need to configure environment variables in the Render dashboard

## Local Development

1. Clone this repository
2. Create a `.env` file in the server directory with required environment variables
3. Install dependencies: `cd server && pip install -r requirements.txt`
4. Run the development server: `uvicorn server.main:app --reload`

## Environment Variables

See `.env.example` for required environment variables. 