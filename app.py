import streamlit as st
import mysql.connector
from datetime import datetime,timedelta
import random
import json
import numpy as np
import pickle

from fpdf import FPDF

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText


from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression

# 1. Load intents.json
with open('intents.json') as file:
    data = json.load(file)

# 2. Prepare training data
texts = []     # X - inputs
labels = []    # y - tags

for intent in data['intents']:
    for pattern in intent['patterns']:
        texts.append(pattern)
        labels.append(intent['tag'])

# 3. Vectorize texts
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(texts)

# 4. Encode labels
label_encoder = LabelEncoder()
y = label_encoder.fit_transform(labels)

# 5. Train the model
model = LogisticRegression()
model.fit(X, y)

# 6. Save the model, vectorizer, and label encoder
with open('model.pkl', 'wb') as model_file:
    pickle.dump(model, model_file)

with open('vectorizer.pkl', 'wb') as vec_file:
    pickle.dump(vectorizer, vec_file)

with open('label_encoder.pkl', 'wb') as le_file:
    pickle.dump(label_encoder, le_file)

print("✅ Training done and files saved: model.pkl, vectorizer.pkl, label_encoder.pkl")

# Database connection setup
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",    # your host
        user="root",         # your MySQL user
        password="",         # your MySQL password
        database="moviedb",  # your database
    )

def check_login(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    conn.close()

    if user is None:
        return False  # User not found
    return user[2] == password  # user[2] is the plain-text password

# Register new user
def register_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if username already exists
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    
    if user:
        conn.close()
        return False  # Username already exists

    # Insert new user into database with plain text password
    cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
    conn.commit()
    conn.close()
    
    return True

# Show login page
def login():
    st.title("🔐 Login Page")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if check_login(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.expecting = 'greeting'  # Start the chatbot flow
            st.session_state.messages = []  # Clear previous messages
            st.success("Login successful! Redirecting to chatbot...")
        else:
            st.error("Invalid credentials. Please try again.")

# Show registration page
def register():
    st.title("📋 Sign-Up Page")
    username = st.text_input("Choose Username")
    password = st.text_input("Choose Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")
    
    if st.button("Sign Up"):
        if password != confirm_password:
            st.error("❌ Passwords do not match!")
        elif register_user(username, password):
            st.success("✅ Registration successful! You can now log in.")
        else:
            st.error("❌ Username already exists.")
# Function to load all movies
def load_movies():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM movies")
    movies = cursor.fetchall()
    cursor.close()
    connection.close()
    return movies

# Function to add a new movie
def save_movie(name, genre, rating, available_seats):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO movies (name, genre, rating, available_seats) VALUES (%s, %s, %s, %s)",
        (name, genre, rating, available_seats)
    )
    connection.commit()
    cursor.close()
    connection.close()

# Function to update seats after booking
def update_available_seats(movie_id,available_seats):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE movies SET available_seats = %s WHERE id = %s",
        (available_seats,movie_id)
    )
    connection.commit()
    cursor.close()
    connection.close()

# Function to load all bookings
def load_bookings():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT b.id, b.name, b.email, b.phone, m.name as movie_name, b.booking_time "
        "FROM bookings b JOIN movies m ON b.movie_id = m.id"
    )
    bookings = cursor.fetchall()
    cursor.close()
    connection.close()

    return bookings
# Function to save a booking
def save_booking(name, email, phone, movie_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    booking_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO bookings (name, email, phone, movie_id, booking_time) VALUES (%s, %s, %s, %s, %s)",
        (name, email, phone, movie_id, booking_time)
    )
    booking_id = cursor.lastrowid  # ✅ Fetch the auto-incremented ID from DB
    connection.commit()
    cursor.close()
    connection.close()
    return booking_id

with open('intents.json',) as file:
    intents = json.load(file)

def chatbot_response(user_message):
    user_message = user_message.lower()

    for intent in intents['intents']:
        for pattern in intent['patterns']:
                return random.choice(intent['responses'])

    return "Sorry, I didn't understand that. Can you please rephrase?"

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'expecting' not in st.session_state:
    st.session_state.expecting = None
if 'selected_movie' not in st.session_state:
    st.session_state.selected_movie = None
if 'booking_info' not in st.session_state:
    st.session_state.booking_info = {}

# BOOKING_FILE = 'bookings.json'
#def sanitize_text(text):
    #return text.encode('latin-1', 'replace').decode('latin-1')

def sanitize_text(text):
    return ''.join(c for c in text if c.isalnum() or c in ' .,-')


def generate_ticket_pdf(booking_info):
    pdf = FPDF('P', 'mm', (80, 150))  # Ticket-like size
    pdf.add_page()

    RED = (190, 30, 45)
    CREAM = (255, 245, 230)

    # Top Banner
    pdf.set_fill_color(*RED)
    pdf.rect(0, 0, 80, 40, 'F')

    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(0, 5)
    pdf.cell(80, 7, "E-TICKET", ln=True, align='C')

    pdf.set_font("Arial", 'B', 25)
    pdf.cell(60, 10, sanitize_text(booking_info['movie']), ln=True, align='C')

    # Cream Background Body
    pdf.set_fill_color(*CREAM)
    pdf.rect(0, 40, 80, 110, 'F')

    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(0, 45)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(80, 8, "Movie Details", ln=True, align='C')

    # Separator Line
    pdf.set_draw_color(0, 0, 0)
    for x in range(5, 75, 5):
        pdf.line(x, 55, x+2, 55)

    # Seat Info
    pdf.set_font("Arial", 'B', 12)
    pdf.set_xy(5, 60)
    pdf.cell(23, 10, "BLOCK", ln=0)
    pdf.cell(23, 10, "ROW", ln=0)
    pdf.cell(23, 10, "SEAT", ln=1)

    block = random.randint(1, 5)
    row = random.randint(1, 20)
    seat = random.randint(1, 50)

    pdf.set_font("Arial", '', 12)
    pdf.set_x(5)
    pdf.cell(23, 8, f"{block:02d}", ln=0)
    pdf.cell(23, 8, f"{row:02d}", ln=0)
    pdf.cell(23, 8, f"{seat:02d}", ln=1)

    # Date & Time
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.set_x(5)
    pdf.cell(35, 10, "DATE", ln=0)
    pdf.cell(35, 10, "TIME", ln=1)

    pdf.set_font("Arial", '', 12)
    booking_date, booking_time = booking_info['booking_time'].split()
    pdf.set_x(5)
    pdf.cell(35, 8, booking_date, ln=0)

    # Convert showtiming (timedelta) to 12-hour format
    td = booking_info['show_time']
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    show_time = f"{hours % 12 or 12}:{minutes:02} {'AM' if hours < 12 else 'PM'}"

    pdf.cell(35, 8, show_time, ln=1)

    # Dashed Line Decor
    pdf.set_y(120)
    pdf.set_fill_color(0, 0, 0)
    for i in range(10, 70, 3):
        pdf.rect(i, 125, 1, 15, 'F')

    # Ticket ID
    pdf.set_font("Arial", '', 10)
    pdf.set_y(110)
    ticket_id = random.randint(1000, 9999)
    pdf.cell(0, 10, f"TICKET #{ticket_id}", 0, 0, 'C')

    # Output
    file_name = f"ticket_{sanitize_text(booking_info['name'].replace(' ', '_'))}.pdf"
    pdf.output(file_name)
    return file_name

    # start_time = datetime.strptime("10:00 AM", "%I:%M %p")
    # random_minutes = random.randint(0, 180)  # Random time within 3 hours after 10:00 AM
    # show_time = start_time + timedelta(minutes=random_minutes)

    # pdf.set_font("Arial", '', 12)
    # pdf.set_x(5)
    # pdf.cell(30, 8, booking_info['booking_time'].split()[0], ln=0)
    # pdf.cell(30, 8, show_time.strftime("%I:%M %p"), ln=1)
    
    
def send_email_with_ticket(to_email, pdf_path):
    sender_email = "2004sanket@gmail.com"
    sender_password = "uqmkexvxeocxarbc"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = "🎟️ Your Movie Ticket Confirmation"

    body = "Thank you for your booking! Please find your ticket attached."
    msg.attach(MIMEText(body, 'plain'))

    with open(pdf_path, "rb") as file:
        part = MIMEApplication(file.read(), Name=pdf_path)
        part['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)

def delete_booking(booking_id):
    num_tickets = st.session_state.num_tickets
    
    connection = get_db_connection()
    cursor = connection.cursor()
    # First get the movie_id from booking
    cursor.execute("SELECT movie_id FROM bookings WHERE booking_id = %s", (booking_id,))
    booking = cursor.fetchone()
    if booking:
        movie_id = booking[0]
        # Delete the booking
        cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
        # Increase available seats back by 1
        cursor.execute("UPDATE movies SET available_seats = available_seats - %s WHERE id = %s", (num_tickets,movie_id,))
        connection.commit()
    cursor.close()
    connection.close()
# Display Streamlit UI
st.title("🎬 TicketGenie: Movie Booking Chatbot")

def calculate_price(movie_id, num_tickets):
    movie = next((m for m in load_movies() if m['id'] == movie_id), None)
    
    if movie:
        price_per_ticket = movie['Price']  # Price per ticket fetched from the database
        
        # Calculate total price based on the number of tickets
        total_price = price_per_ticket * num_tickets
        return total_price
    return 0 
# Custom CSS for styling
st.markdown("""
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #F0F4F8;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }

        .chat-container {
            width: 400px;
            max-width: 100%;
            background-color: white;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
        }

        .chat-box {
            flex-grow: 1;
            overflow-y: auto;
            margin-bottom: 20px;
            max-height: 400px;
        }

        .chat-message {
            padding: 12px;
            margin: 10px 0;
            border-radius: 10px;
            max-width: 70%;
        }

        .user-message {
            background-color: #3b7ddd;
            color: white;
            align-self: flex-end;
        }

        .assistant-message {
            background-color: #f1f1f1;
            color: black;
            align-self: flex-start;
        }

        .input-container {
            display: flex;
        }

        #user-input {
            flex-grow: 1;
            padding: 12px;
            border-radius: 25px;
            border: 1px solid #ccc;
        }

        #send-button {
            background-color: #3b7ddd;
            color: white;
            border: none;
            padding: 12px 18px;
            border-radius: 25px;
            cursor: pointer;
            margin-left: 10px;
        }

        #send-button:hover {
            background-color: #357bbd;
        }

        .title {
            font-size: 24px;
            text-align: center;
            color: #333;
        }
    </style>
""", unsafe_allow_html=True)

# Create a container for the chatbox
with st.container():
    # Display messages from chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg['role']):
            if msg['role'] == 'user':
                st.markdown(f'<div class="chat-message user-message">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-message assistant-message">{msg["content"]}</div>', unsafe_allow_html=True)

# Get user input
user_input = st.chat_input("Type your message...")
def chatbot():
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        if st.session_state.expecting == "greeting":
            if intent == "greeting":
                bot_reply = "👋 Hello! Would you like to book a movie?"
            elif intent == "book_movie":
                movies = load_movies()
                bot_reply = "🎬 Here are the movies:\n\n"
                for movie in movies:
                    bot_reply += f"- ID: {movie['id']}, Name: {movie['name']},Price:{movie['Price']}, Seats: {movie['available_seats']}\n"
                st.session_state.expecting = "movie_id"
            else:
                bot_reply = "🤖 I'm here to help! Say 'hello' or 'book a movie' to get started."   
    
        if st.session_state.expecting == 'movie_id':
        # In the section where you handle movie selection
            if user_input.isdigit():
                movie_id = int(user_input)
                selected_movie = next((m for m in load_movies() if m['id'] == movie_id), None)
    
                if selected_movie:
                    if selected_movie['available_seats']>0:
                        st.session_state.selected_movie = selected_movie
                        bot_reply = f"You selected **{selected_movie['name']}**.\n\nHow many tickets would you like to book? (Available: {selected_movie['available_seats']})"
                        st.session_state.expecting = 'num_tickets'
                    else:
                        bot_reply = f"💔 Sorry, **{selected_movie['name']}** has **no available seats**. Please select another movie."
                else:
                    bot_reply = "💔 Invalid movie ID. Please try again."
            else:
                bot_reply = "Please enter a valid numeric movie ID."

        elif st.session_state.expecting == 'num_tickets':
            if user_input.isdigit():
                num_tickets = int(user_input)
                if 1 <= num_tickets <= st.session_state.selected_movie['available_seats']:
                    st.session_state.num_tickets = num_tickets
                    total_price = calculate_price(st.session_state.selected_movie['id'], num_tickets)

            # Show the total price and ask for user info
                    bot_reply = f"Great! The total price for {num_tickets} tickets is ₹{total_price}. Now, please enter your **Name, Email, and Phone**, separated by commas."

                    st.session_state.expecting = 'user_info'
                else:
                    bot_reply = f"⚠️ Please enter a number between 1 and {st.session_state.selected_movie['available_seats']}."
            else:
                bot_reply = "Please enter a valid number for tickets."

        elif st.session_state.expecting == 'user_info':
            parts = user_input.split(',')
        
            if len(parts) == 3:
                name, email, phone = [p.strip() for p in parts]
                booking_id = save_booking(name, email, phone, st.session_state.selected_movie['id'])
                num_tickets = st.session_state.num_tickets

                update_available_seats(
                st.session_state.selected_movie['id'],
                st.session_state.selected_movie['available_seats'] - st.session_state.num_tickets
                ) # Update the available seats after booking
           
                st.session_state.booking_info = {
                    "booking_id":booking_id,
                    "name":sanitize_text( name),
                    "email": sanitize_text(email),
                    "phone": sanitize_text(phone),
                    "movie": st.session_state.selected_movie['name'],
                    "show_date": st.session_state.selected_movie["Date"],
                    "booking_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "show_time": st.session_state.selected_movie["showtiming"]
                }
            
                show_date = st.session_state.booking_info["show_date"].strftime("%d-%b-%Y")
            
                td = st.session_state.booking_info["show_time"]
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                show_time = f"{hours % 12 or 12}:{minutes:02} {'AM' if hours < 12 else 'PM'}"
            
                bot_reply = (
                    f"📧 **Booking Successful!**<br>"
                    f"🆔 Booking ID: {booking_id}<br>"
                    f"🎬 Movie: {st.session_state.booking_info['movie']}<br>"
                    f"📅 Date: {show_date}<br>"
                    f"⏰ Time: {show_time}<br>"
                    f"👤 Name: {name}<br>"
                    f"📧 Email: {email}<br>"
                    f"📞 Phone: {phone}"
    
                    )
            # bot_reply = f"📧 **Booking Successful!**\n\nBooking ID:{booking_id}🎬 Movie: {st.session_state.selected_movie}\n👤 Name: {name}\n📧 Email: {email}\n📞 Phone: {phone}\n⏰ Time: {st.session_state.booking_info['booking_time']}"
                st.success("Your ticket has been booked successfully! 🎉")
            

# Generate ticket PDF
                pdf_file = generate_ticket_pdf(st.session_state.booking_info)
                send_email_with_ticket(email, pdf_file)


# Download button for the ticket
                with open(pdf_file, "rb") as f:
                    st.download_button(
                    label="🎟️ Download your Ticket",
                    data=f,
                    file_name=pdf_file,
                    mime="application/pdf",
                )
                
                    bot_reply+="\n\n❓ Do you want to delete any ticket? (yes/no)"
                    st.session_state.expecting = 'delete_prompt'
            else:   
                bot_reply = "Please enter **Name, Email, and Phone** properly, separated by commas."
        elif st.session_state.expecting=='delete_prompt':
            if user_input.lower() in ['yes','y']:
                bot_reply="Pls enter Booking ID you want to delete."
                st.session_state.expecting='delete_ticket'
            else:
                bot_reply = "Alright! Thanks for using our service! 🎬✨"
                st.session_state.expecting = None
                st.session_state.selected_movie = None
                st.session_state.num_tickets = None
    
        elif st.session_state.expecting == 'delete_ticket':
            if user_input.isdigit():
                booking_id = int(user_input)
                delete_booking(booking_id)
                bot_reply = f"✅ Successfully deleted booking with ID {booking_id}!"
                st.session_state.expecting = None
                st.session_state.selected_movie = None
                st.session_state.num_tickets = None
            else:
                bot_reply = "Please enter a valid Booking ID."
      
        else:
            if "book movie" in user_input.lower() or "book ticket" in user_input.lower():
    # your logic here
                movie_list = "\n".join([f"{m['id']}. {m['name']} ({m['genre']}, Rating: {m['rating']},Date: {datetime.strptime(str(m['Date']), '%Y-%m-%d').strftime('%d-%b-%Y')} Showtime: {datetime.strptime(str(m['showtiming']), '%H:%M:%S').strftime('%I:%M %p')},Price:{m['Price']}, Available Seats: {m['available_seats']})" for m in load_movies()])
                bot_reply = f"Here are the available movies:\n\n{movie_list}\n\nPlease enter the **Movie ID** to book."
                st.session_state.expecting = 'movie_id'
            else:
                bot_reply = chatbot_response(user_input)

        st.session_state.messages.append({"role": "assistant", "content": bot_reply})

        with st.chat_message("assistant"):
            st.markdown(f'<div class="chat-message assistant-message">{bot_reply}</div>', unsafe_allow_html=True)

        if st.session_state.booking_info:
            with st.expander("🌍 View your booking summary"):
                st.json(st.session_state.booking_info)

if not st.session_state.logged_in:
    choice = st.sidebar.radio("Select Page", ("Login", "Sign Up"))
    if choice == "Login":
        login()
    elif choice == "Sign Up":
        register()
else:
    chatbot()
