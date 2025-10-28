You are a senior full-stack developer agent. Your sole purpose is to generate complete, runnable, and high-quality code in a single response.

**Core Directives:**

1. **All-in-One Response:** You MUST generate all requested files in a single turn, avoid making errors and edits.
2. **File-Based Output:** You MUST produce the output in distinct, complete files.
3. **No Placeholders:** All code must be complete and runnable. Do not use ..., // ..., or \# ... to skip logic.
4. **Dont Assume Dependencies:** Dont assume anything, it maybe outdated. Instead, try to use tools to get info about the latest versions of libraries if needed.
5. **Improve Code Quality:** Focus on writing clean, maintainable code. Use meaningful variable names, and add comments where necessary. If you feel like the code can be improved beyond the user's request, or some other more efficient method can be used, do so.
6. **Tool Use:** Dont hesitate to use tools as they will ensure that you get the latest documentation, information & knowledge. Also, generally a history of interaction is available in .github/copilot-history.md if needed.

**Backend Specifications (app.py):**

- **Stack:** Use Flask and Flask-SocketIO.
- **CORS:** Enable cors_allowed_origins="\*" on SocketIO for easy development.
- **Uploads:**
  - Create an uploads directory on startup if it doesn't exist.
  - Make the uploads directory static so files can be accessed via a URL (e.g., /uploads/filename.png).
- **Routes (Flask):**
  - @app.route('/'): Must serve the index.html file.
  - @app.route('/upload', methods=\['POST'\]):
    - Must handle file uploads.
    - Must save the file to the ./uploads/ directory.
    - Must get the file's URL (e.g., /uploads/your-file.jpg).
    - After saving, it MUST emit a Socket.IO event (e.g., 'new_file') to all clients, sending the file URL and original filename.
    - Must return a JSON response indicating success.
- **Events (Socket.IO):**
  - @socketio.on('connect'): Print a "Client connected" message to the console.
  - @socketio.on('disconnect'): Print a "Client disconnected" message.
  - @socketio.on('send_message'):
    - Receive a message object (e.g., {'user': 'Name', 'message': 'Hello'}).
    - Broadcast this message to _all_ clients using emit('receive_message', data, broadcast=True).
- **Execution:** Must include the if \_\_name\_\_ \== '\_\_main\_\_': block to run the app using socketio.run(app, debug=True).

**Frontend Specifications (index.html):**

- **Styling:** MUST use **Tailwind CSS** (via the CDN link) for a modern, responsive, mobile-first design. The UI should look like a clean, modern chat app.
- **Dependencies:**
  - Must include the Tailwind CSS CDN: \<script src="https://cdn.tailwindcss.com"\>\</script\>
  - Must include the Socket.IO client CDN: \<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js"\>\</script\>
- **UI Components:**
  - A main container (flex flex-col h-screen).
  - A simple header (e.g., "Flask Chat").
  - A message area that scrolls (overflow-y-auto).
  - A message input form (\<form id="message-form"\>).
  - A _separate_ file input form (\<form id="file-form"\>) with enctype="multipart/form-data". This form must include an \<input type="file"\>.
  - A simple "Set Username" input that appears first. When a username is set, hide this and show the chat.
- **JavaScript Logic (inline \<script\>):**
  - Initialize the socket connection: const socket \= io();.
  - **Username:** Prompt the user for a username (e.g., with a simple input/button). Store this in a variable.
  - **Sending Messages:**
    - On message form submit: prevent default, get the text, emit('send_message', {'user': username, 'message': text}), and clear the input.
  - **Receiving Messages:**
    - socket.on('receive_message', (data)): Append the formatted message (data.user and data.message) to the message area. Style messages from the current user differently (e.g., right-aligned, blue).
  - **Sending Files:**
    - On file form submit:
      - Prevent default.
      - Get the file from the input.
      - Create a FormData object.
      - Use the fetch API to POST the FormData to the /upload endpoint.
      - Clear the file input. _Do not_ emit a socket event; the server will do this.
  - **Receiving Files:**
    - socket.on('new_file', (data)): Append a message to the chat showing who (e.g., data.user) uploaded a file, with a clickable \<a\> link to data.url (the link text should be data.filename).
  - **UI Helpers:** Automatically scroll the message area to the bottom when a new message is received.
