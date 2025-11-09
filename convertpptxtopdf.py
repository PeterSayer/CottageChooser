import os
import sys
import win32com.client
from pathlib import Path

def convert_pptx_to_images():
    # Get absolute paths
    script_dir = Path(__file__).parent.absolute()
    input_path = script_dir / 'static' / 'presentation.pptx'
    output_dir = script_dir / 'static' / 'slides'
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Converting presentation: {input_path}")
    print(f"Saving slides to: {output_dir}")
    
    try:
        # Initialize PowerPoint
        powerpoint = win32com.client.Dispatch('PowerPoint.Application')
        powerpoint.Visible = True  # Make PowerPoint visible for debugging
        
        # Open the presentation
        print("Opening PowerPoint presentation...")
        presentation = powerpoint.Presentations.Open(str(input_path))
        print(f"Found {presentation.Slides.Count} slides")
        
        # Export each slide
        for i in range(1, presentation.Slides.Count + 1):
            image_path = output_dir / f'slide-{i:03d}.png'
            print(f"Exporting slide {i} to {image_path}")
            presentation.Slides(i).Export(str(image_path), 'PNG')
            
        print("Conversion completed successfully!")
        
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        raise
    finally:
        try:
            # Clean up
            presentation.Close()
            powerpoint.Quit()
        except:
            pass  # Ignore errors during cleanup

if __name__ == '__main__':
    try:
        convert_pptx_to_images()
    except Exception as e:
        print(f"Failed to convert presentation: {e}", file=sys.stderr)
        sys.exit(1)