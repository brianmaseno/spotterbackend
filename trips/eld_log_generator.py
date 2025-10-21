"""
ELD Log Generator
Creates Driver's Daily Log sheets in PDF format
Following FMCSA regulations and format requirements
"""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from datetime import datetime, timedelta
from typing import List, Dict
import io


class ELDLogGenerator:
    """
    Generate ELD (Electronic Logging Device) logs in FMCSA format
    """
    
    # Page dimensions
    PAGE_WIDTH, PAGE_HEIGHT = letter
    MARGIN = 0.5 * inch
    
    # Grid settings
    GRID_START_X = MARGIN
    GRID_START_Y = PAGE_HEIGHT - 4.5 * inch
    GRID_WIDTH = PAGE_WIDTH - 2 * MARGIN
    GRID_HEIGHT = 2 * inch
    
    # Duty status rows (from top to bottom)
    ROW_HEIGHT = GRID_HEIGHT / 4
    
    def __init__(self):
        pass
    
    def generate_daily_logs(self, daily_logs: List[Dict], 
                           driver_info: Dict) -> bytes:
        """
        Generate PDF with all daily logs
        
        Args:
            daily_logs: List of daily log dictionaries
            driver_info: Driver and carrier information
            
        Returns:
            PDF bytes
        """
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        
        for log in daily_logs:
            self._draw_daily_log(pdf, log, driver_info)
            pdf.showPage()
        
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()
    
    def _draw_daily_log(self, pdf: canvas.Canvas, log: Dict, driver_info: Dict):
        """
        Draw a single daily log page
        """
        # Header
        self._draw_header(pdf, log, driver_info)
        
        # Graph grid
        self._draw_grid(pdf)
        
        # Fill in duty status
        self._draw_duty_status(pdf, log)
        
        # Remarks section
        self._draw_remarks(pdf, log)
        
        # Total hours
        self._draw_totals(pdf, log)
    
    def _draw_header(self, pdf: canvas.Canvas, log: Dict, driver_info: Dict):
        """
        Draw log header with date, driver info, etc.
        """
        y = self.PAGE_HEIGHT - self.MARGIN
        
        # Title
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(self.MARGIN, y, "Driver's Daily Log")
        y -= 0.3 * inch
        
        # Date
        pdf.setFont("Helvetica", 12)
        date_str = log['date'].strftime("%m/%d/%Y")
        pdf.drawString(self.MARGIN, y, f"Date: {date_str}")
        
        # Total miles
        pdf.drawString(3.5 * inch, y, f"Total Miles: {int(log['total_miles'])}")
        y -= 0.25 * inch
        
        # Driver name
        pdf.setFont("Helvetica", 10)
        pdf.drawString(self.MARGIN, y, f"Driver: {driver_info.get('driver_name', 'N/A')}")
        y -= 0.2 * inch
        
        # Carrier info
        pdf.drawString(self.MARGIN, y, f"Carrier: {driver_info.get('carrier_name', 'N/A')}")
        y -= 0.2 * inch
        
        pdf.drawString(self.MARGIN, y, f"Main Office: {driver_info.get('main_office', 'N/A')}")
        y -= 0.2 * inch
        
        # Truck/Trailer numbers
        pdf.drawString(self.MARGIN, y, 
                      f"Vehicle: {driver_info.get('vehicle_number', 'N/A')}")
        y -= 0.3 * inch
        
        # 24-hour period note
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.drawString(self.MARGIN, y, "(24-hour period starting midnight)")
    
    def _draw_grid(self, pdf: canvas.Canvas):
        """
        Draw the duty status graph grid
        """
        x = self.GRID_START_X
        y = self.GRID_START_Y
        
        # Draw outer rectangle
        pdf.setStrokeColor(colors.black)
        pdf.setLineWidth(1.5)
        pdf.rect(x, y, self.GRID_WIDTH, self.GRID_HEIGHT)
        
        # Draw horizontal lines (4 duty status rows)
        pdf.setLineWidth(0.5)
        for i in range(1, 4):
            y_line = y + (i * self.ROW_HEIGHT)
            pdf.line(x, y_line, x + self.GRID_WIDTH, y_line)
        
        # Draw vertical lines (24 hours + midnight markers)
        hour_width = self.GRID_WIDTH / 24
        for i in range(1, 24):
            x_line = x + (i * hour_width)
            # Thicker lines for every 2 hours
            if i % 2 == 0:
                pdf.setLineWidth(0.8)
            else:
                pdf.setLineWidth(0.3)
            pdf.line(x_line, y, x_line, y + self.GRID_HEIGHT)
        
        # Hour labels
        pdf.setFont("Helvetica", 7)
        for i in range(25):
            if i % 2 == 0 or i == 12:  # Label every 2 hours and noon
                hour_label = "Mid" if i == 0 or i == 24 else ("Noon" if i == 12 else str(i))
                label_x = x + (i * hour_width) - 8
                pdf.drawString(label_x, y + self.GRID_HEIGHT + 5, hour_label)
        
        # Duty status labels (on the left)
        pdf.setFont("Helvetica", 9)
        status_labels = ["Off Duty", "Sleeper Berth", "Driving", "On Duty\n(Not Driving)"]
        for i, label in enumerate(status_labels):
            label_y = y + self.GRID_HEIGHT - ((i + 0.5) * self.ROW_HEIGHT)
            # Draw label to the left of grid
            pdf.drawString(x - 80, label_y - 5, label)
    
    def _draw_duty_status(self, pdf: canvas.Canvas, log: Dict):
        """
        Draw duty status lines on the grid
        """
        x = self.GRID_START_X
        y = self.GRID_START_Y
        hour_width = self.GRID_WIDTH / 24
        
        # Map duty status to row (0 = top, 3 = bottom)
        status_to_row = {
            'off_duty': 0,
            'sleeper_berth': 1,
            'driving': 2,
            'on_duty_not_driving': 3
        }
        
        # Draw lines for each activity
        pdf.setStrokeColor(colors.blue)
        pdf.setLineWidth(2)
        
        current_time = log['date'].replace(hour=0, minute=0, second=0)
        
        for activity in log['activities']:
            start_time = activity['start_time']
            
            # Calculate start hour (0-24)
            time_diff = (start_time - log['date']).total_seconds() / 3600
            if time_diff < 0:
                continue  # Skip activities from previous day
            if time_diff >= 24:
                break  # Stop at activities from next day
            
            start_hour = time_diff
            end_hour = min(start_hour + activity['duration_hours'], 24)
            
            # Get row for this duty status
            row = status_to_row.get(activity['duty_status'], 3)
            line_y = y + self.GRID_HEIGHT - ((row + 0.5) * self.ROW_HEIGHT)
            
            # Draw horizontal line
            start_x = x + (start_hour * hour_width)
            end_x = x + (end_hour * hour_width)
            pdf.line(start_x, line_y, end_x, line_y)
            
            # Draw vertical transitions
            if activity != log['activities'][0]:  # Not the first activity
                # Draw vertical line from previous status
                prev_activity = log['activities'][log['activities'].index(activity) - 1]
                prev_row = status_to_row.get(prev_activity['duty_status'], 3)
                if prev_row != row:
                    prev_y = y + self.GRID_HEIGHT - ((prev_row + 0.5) * self.ROW_HEIGHT)
                    pdf.line(start_x, prev_y, start_x, line_y)
    
    def _draw_remarks(self, pdf: canvas.Canvas, log: Dict):
        """
        Draw remarks section with activity details and locations (FMCSA compliant)
        """
        y = self.GRID_START_Y - 0.3 * inch
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(self.MARGIN, y, "REMARKS (Location for each duty status change):")
        y -= 0.15 * inch
        
        pdf.setFont("Helvetica", 8)
        
        # Build remarks with city, state for each duty status change
        remarks = []
        for activity in log['activities']:
            # Get location info
            location_info = activity.get('location_info', {})
            city = location_info.get('city', 'Unknown')
            state = location_info.get('state', 'Unknown')
            location_str = f"{city}, {state}"
            
            time_str = activity['start_time'].strftime("%I:%M %p")
            
            # Only show significant activities and duty status changes
            if activity['duty_status'] in ['driving', 'on_duty_not_driving'] or 'Break' in activity['activity']:
                remark = f"{time_str} - {activity['activity']} ({location_str})"
                if activity.get('description') and len(activity['description']) > 0:
                    remark += f": {activity['description'][:50]}"
                
                remarks.append(remark)
        
        # Draw remarks
        for remark in remarks[:15]:  # Limit to 15 remarks to avoid overflow
            pdf.drawString(self.MARGIN + 10, y, remark[:120])  # Limit length
            y -= 0.12 * inch
            
            # Stop if we run out of space
            if y < self.MARGIN + 0.5 * inch:
                break
    
    def _draw_totals(self, pdf: canvas.Canvas, log: Dict):
        """
        Draw total hours summary
        """
        x = self.PAGE_WIDTH - 2.5 * inch
        y = self.GRID_START_Y + self.GRID_HEIGHT + 0.5 * inch
        
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x, y, "Total Hours:")
        y -= 0.15 * inch
        
        pdf.setFont("Helvetica", 9)
        
        totals = [
            ("Off Duty:", log['total_off_duty']),
            ("Sleeper Berth:", log['total_sleeper']),
            ("Driving:", log['total_driving']),
            ("On Duty:", log['total_on_duty']),
        ]
        
        for label, hours in totals:
            pdf.drawString(x, y, f"{label} {hours:.1f} hrs")
            y -= 0.12 * inch
        
        # Verify 24 hours total
        total = log['total_off_duty'] + log['total_sleeper'] + log['total_driving'] + log['total_on_duty']
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x, y - 0.1 * inch, f"Total: {total:.1f} hrs")
    
    def generate_log_preview_data(self, daily_logs: List[Dict]) -> List[Dict]:
        """
        Generate JSON data for frontend preview of logs
        
        Returns simplified log data for display
        """
        preview_data = []
        
        for log in daily_logs:
            preview_data.append({
                'date': log['date'].isoformat(),
                'total_miles': round(log['total_miles'], 1),
                'total_driving': round(log['total_driving'], 1),
                'total_on_duty': round(log['total_on_duty'], 1),
                'total_off_duty': round(log['total_off_duty'], 1),
                'total_sleeper': round(log['total_sleeper'], 1),
                'activities': [
                    {
                        'time': activity['start_time'].strftime("%I:%M %p"),
                        'activity': activity['activity'],
                        'duty_status': activity['duty_status'],
                        'duration_hours': round(activity['duration_hours'], 2),
                        'description': activity.get('description', '')
                    }
                    for activity in log['activities']
                ]
            })
        
        return preview_data
