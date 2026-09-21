# Placement Assistant — Day 2 Agentic AI                                                                                          
                                                                                                                                      
    An intelligent campus placement assistant capable of querying student eligibility, discovering open recruitment drives, scheduling
  interview slots, and maintaining persistent conversation memory across sessions using SQLite and Google Gemini.                     
                                                                                                                                      
    ---                                                                                                                               
                                                                                                                                      
    ## 🏗️ Architecture Overview                                                                                                       
                                                                                                                                      
                                                                                                                                      
  User Query (CLI / Chat)                                                                                                             
  │                                                                                                                                   
  ▼                                                                                                                                   
  Agent Core (app/agent.py)                                                                                                           
  ├── Memory Loader (app/memory.py ◄──► agent.db SQLite)                                                                              
  ├── Model Provider (Gemini / Mock Provider)                                                                                         
  └── Tool Execution Loop                                                                                                             
  │                                                                                                                                   
  ├──► get_student(roll_no)                                                                                                           
  ├──► list_open_drives(min_cgpa, department)                                                                                         
  ├──► get_company(company_id)                                                                                                        
  ├──► list_interview_slots(drive_id)                                                                                                 
  ├──► book_interview_slot(student_id, slot_id)                                                                                       
  └──► notify_student(student_id, message)                                                                                            
                                                                                                                                      
                                                                                                                                      
    ---                                                                                                                               
                                                                                                                                      
    ## 📁 Project Structure                                                                                                           
                                                                                                                                      
    ```text                                                                                                                           
    placement-assistant/                                                                                                              
    ├── app/                                                                                                                          
    │   ├── agent.py                 # Core agent loop, prompt, and tool invocation                                                   
    │   ├── memory.py                # SQLite conversation history & session persistence                                              
    │   ├── providers.py             # LLM provider wrapper (Gemini & Scripted Mock)                                                  
    │   ├── placement_db.py          # In-memory student & placement drive dataset                                                    
    │   └── tools/                                                                                                                    
    │       ├── dispatch.py          # Dynamic tool registration and dispatcher                                                       
    │       └── placement_tools.py   # Read-only and side-effect placement tools                                                      
    ├── schema/                                                                                                                       
    │   └── agent.sql                # SQLite schema for sessions and conversation history                                            
    ├── scripts/                                                                                                                      
    │   ├── chat.py                  # Interactive terminal chat CLI                                                                  
    │   └── demo.py                  # Automated end-to-end demonstration runner                                                      
    ├── tests/                                                                                                                        
    │   ├── test_part1_tools.py      # Unit tests for placement tools                                                                 
    │   ├── test_part2_agent.py      # Tests for agent tool calling and reasoning loop                                                
    │   ├── test_part3_memory.py     # Tests for session memory and message persistence                                               
    │   └── test_lab_notify.py       # Tests for notification and paginated history                                                   
    ├── HANDOUT.html                 # Complete assignment instructions & walkthrough                                                 
    ├── requirements.txt             # Dependencies (google-genai, pytest, pydantic)                                                  
    └── README.md                    # Project documentation                                                                          
  ──────                                                                                                                              
  ## 🧩 Key Components                                                                                                                
                                                                                                                                      
  ### 1. Tools (app/tools/placement_tools.py)                                                                                         
                                                                                                                                      
  • get_student(roll_no: str): Retrieves student profile, CGPA, department, and placement status.                                     
  • list_open_drives(department: str = None): Filters upcoming placement drives based on department and minimum eligibility criteria. 
  • get_company(company_id: str): Retrieves hiring criteria, CTC/package, and role details.                                           
  • list_interview_slots(drive_id: str): Lists available time slots for a specific drive.                                             
  • book_interview_slot(roll_no: str, slot_id: str): Side-effect tool that books an interview slot and decrements capacity atomically.
  • notify_student(roll_no: str, message: str): Sends automated notifications to student records.                                     
                                                                                                                                      
  ### 2. Autonomous Agent Loop (app/agent.py)                                                                                         
                                                                                                                                      
  • Evaluates user intent and dynamically determines which tool(s) to execute.                                                        
  • Chains tool calls (e.g. get_student → list_open_drives → book_interview_slot).                                                    
  • Synthesizes user-friendly responses grounded strictly in tool observations.                                                       
                                                                                                                                      
  ### 3. Persistent Session Memory (app/memory.py & schema/agent.sql)                                                                 
                                                                                                                                      
  • Backed by SQLite database (agent.db).                                                                                             
  • Tracks active sessions via conversations table.                                                                                   
  • Persists chronological conversation history (messages table: role, content, tool_calls, created_at).                              
  • Supports session resumption: returning students can continue their conversation without repeating roll numbers or preferences.    
  ──────                                                                                                                              
  ## 🚀 Getting Started                                                                                                               
                                                                                                                                      
  ### 1. Environment Setup                                                                                                            
                                                                                                                                      
    # Create and activate virtual environment                                                                                         
    python3 -m venv .venv                                                                                                             
    source .venv/bin/activate        # On Windows: .venv\Scripts\activate                                                             
                                                                                                                                      
    # Install dependencies                                                                                                            
    pip install -r requirements.txt                                                                                                   
                                                                                                                                      
  ### 2. API Key Configuration (Optional for Live Mode)                                                                               
                                                                                                                                      
  Copy .env.example to .env or export your Gemini API key:                                                                            
                                                                                                                                      
    export GEMINI_API_KEY="your-google-ai-studio-key"                                                                                 
                                                                                                                                      
  (Note: The test suite and --mock mode operate completely offline without requiring an API key or incurring quota costs).            
  ──────                                                                                                                              
  ## 💻 Running the Assistant                                                                                                         
                                                                                                                                      
  ### A. Offline Mock Mode (Zero Quota Usage)                                                                                         
                                                                                                                                      
  Test the agent logic and tool calling using deterministic scripted models:                                                          
                                                                                                                                      
    python -m scripts.chat --mock                                                                                                     
                                                                                                                                      
  ### B. Persistent Memory Mode                                                                                                       
                                                                                                                                      
  Run the agent with persistent SQLite memory across sessions:                                                                        
                                                                                                                                      
    python -m scripts.chat --mock --db agent.db                                                                                       
                                                                                                                                      
  ### C. Live Gemini Mode
  
  Interact with real Google Gemini:
  
    python -m scripts.chat --db agent.db
  ──────
  ## 🧪 Running Tests
  
  The test suite runs 100% offline with zero external API calls:
  
    # Run all tests
    pytest -v
  
    # Run tests step-by-step
    pytest tests/test_part1_tools.py   # Validate placement tools
    pytest tests/test_part2_agent.py   # Validate tool calling loop
    pytest tests/test_part3_memory.py  # Validate SQLite persistence
  ──────
  ## 🛡️ Design Principles
  
  • Least Privilege: Tools validate student eligibility before allowing write side-effects (e.g., ensuring minimum CGPA before booking
  slots).
  • Quota Protection: Separation between mock providers and live API calls ensures tests run fast, reliably, and cost-free.           
  • Safety & Sanitization: SQL queries use parameterized arguments to prevent injection.
