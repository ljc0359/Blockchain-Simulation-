from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz

# Create a new calendar
cal = Calendar()

# Function to create an exam event
def create_exam_event(exam_info):
    event = Event()
    start_time = datetime.strptime(exam_info['date'] + ' ' + exam_info['start_time'], '%A %d %b %Y %I:%M%p')
    duration = timedelta(hours=exam_info['duration_hours'], minutes=exam_info['duration_minutes'])
    end_time = start_time + duration
    
    event.add('summary', f"Exam: {exam_info['exam_name']} - {exam_info['assessment_type']}")
    event.add('dtstart', start_time)
    event.add('dtend', end_time)
    event.add('description', f"Seat: {exam_info['seat']}\\nVenue: {exam_info['venue']} - Room {exam_info['room']}\\nExam Conditions: {exam_info['exam_conditions']}\\nMaterials Permitted: {exam_info['materials_permitted']}\\nMap: {exam_info['map']}")
    event.add('location', f"{exam_info['venue']}, Room {exam_info['room']}, Building {exam_info['building']}")
    
    cal.add_component(event)

# Exam information list
exams = [
    {
        'exam_name': 'COMP3027 Algorithm Design',
        'assessment_type': 'Paper Exam',
        'date': 'Tuesday 04 Jun 2024',
        'start_time': '5:00pm',
        'duration_hours': 2,
        'duration_minutes': 10,
        'seat': '44',
        'venue': 'Quadrangle Building McRae Rm S418',
        'building': 'A14',
        'room': 'S418',
        'map': 'https://link.mazemap.com/0TqTk2k6',
        'exam_conditions': 'RESTRICTED OPEN book exam - specified materials permitted',
        'materials_permitted': 'One A4 sheet of handwritten and/or typed notes double-sided'
    },
    {
        'exam_name': 'COMP3221 Distributed Systems',
        'assessment_type': 'Paper Exam',
        'date': 'Saturday 08 Jun 2024',
        'start_time': '1:00pm',
        'duration_hours': 2,
        'duration_minutes': 10,
        'seat': '5',
        'venue': 'Quadrangle Building Room S227',
        'building': 'A14',
        'room': 'S227',
        'map': 'https://link.mazemap.com/fbJr25wq',
        'exam_conditions': 'CLOSED book exam - no material permitted',
        'materials_permitted': '(Online exam only) Blank scratch paper - 2 sheets'
    },
    {
        'exam_name': 'INFO3333 Computing 3 Management',
        'assessment_type': 'Paper Exam',
        'date': 'Wednesday 12 Jun 2024',
        'start_time': '9:00am',
        'duration_hours': 2,
        'duration_minutes': 10,
        'seat': '15',
        'venue': 'Teachers College Assembly Hall 300',
        'building': 'A22',
        'room': '300',
        'map': 'https://link.mazemap.com/5eNvmqkf',
        'exam_conditions': 'OPEN book exam',
        'materials_permitted': 'Calculator - non-programmable'
    },
    {
        'exam_name': 'COMP2017/COMP9017 Systems Programming',
        'assessment_type': 'Paper Exam',
        'date': 'Friday 14 Jun 2024',
        'start_time': '9:00am',
        'duration_hours': 2,
        'duration_minutes': 10,
        'seat': '58',
        'venue': 'Quadrangle MacLaurin Hall',
        'building': 'A14',
        'room': 'S458',
        'map': 'https://link.mazemap.com/dvIUKeno',
        'exam_conditions': 'CLOSED book exam - no material permitted',
        'materials_permitted': 'Calculator - non-programmable'
    }
]

# Add each exam to the calendar
for exam in exams:
    create_exam_event(exam)

# Save the calendar to an .ics file
file_path = 'Final_Exams_Timetable_500135385.ics'
with open(file_path, 'wb') as f:
    f.write(cal.to_ical())