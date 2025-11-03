#!/usr/bin/env python3
"""
Canvas Quiz to LaTeX/PDF Generator

Processes Canvas quiz export CSV files and generates individual LaTeX files 
(and PDFs) for each student containing only the questions they answered.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
from bs4 import BeautifulSoup


class HTMLToLatexConverter:
    """Converts HTML content to LaTeX format."""
    
    # Special LaTeX characters that need escaping
    LATEX_SPECIAL_CHARS = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }
    
    @staticmethod
    def escape_latex(text: str, preserve_latex: bool = True) -> str:
        """Escape special LaTeX characters in text."""
        # Don't escape if it looks like it's already LaTeX math or commands
        if preserve_latex and re.search(r'\\[a-zA-Z]+|[\$]', text):
            return text
        
        # Only escape characters that aren't part of LaTeX syntax
        result = text
        for char, escaped in HTMLToLatexConverter.LATEX_SPECIAL_CHARS.items():
            if char == '\\' and preserve_latex:
                # Don't escape backslashes that are part of LaTeX commands
                continue
            result = result.replace(char, escaped)
        return result
    
    @staticmethod
    def convert_equation_image(img_tag) -> str:
        """Extract LaTeX from Canvas equation image tags."""
        # Try to get LaTeX from data-equation-content attribute
        latex_content = img_tag.get('data-equation-content', '')
        if latex_content:
            # Wrap in math mode if not already
            if not latex_content.startswith('$'):
                return f'${latex_content}$'
            return latex_content
        
        # Try title attribute as fallback
        title = img_tag.get('title', '')
        if title:
            if not title.startswith('$'):
                return f'${title}$'
            return title
        
        # If no LaTeX found, return empty string
        return ''
    
    @classmethod
    def html_to_latex(cls, html_content: str, is_question: bool = False) -> str:
        """Convert HTML content to LaTeX."""
        if not html_content or pd.isna(html_content):
            return ''
        
        # If it looks like plain text (not HTML), handle it specially
        if not '<' in html_content:
            # Plain text - format for readability
            text = html_content.strip()
            
            # Replace non-breaking spaces and other unicode spaces with regular spaces
            text = text.replace('\u00a0', ' ')  # non-breaking space
            text = text.replace('\u2003', ' ')  # em space
            text = text.replace('\u2002', ' ')  # en space
            
            # Collapse multiple spaces (from missing equations in Canvas export)
            text = re.sub(r'  +', ' ', text)
            
            # Check if this looks like code/algorithm with numbered lines
            # Pattern: "1. ... 2. ... 3. ..." or similar
            if re.search(r'\d+\.\s+', text):
                # Replace numbered lines with actual line breaks for algorithms
                # Match patterns like "2. ", "3. ", etc. but not at the start
                text = re.sub(r'(\d+\.\s+)', r'\n\1', text)
                text = text.strip()  # Remove leading newline
            
            # Preserve existing LaTeX, only escape problematic chars
            if '\\' in text or '$' in text:
                # Has LaTeX - only escape &, %, #
                text = text.replace('&', r'\&')
                text = text.replace('%', r'\%') 
                text = text.replace('#', r'\#')
            else:
                # No LaTeX - escape special chars that would break compilation
                for char in ['&', '%', '$', '#', '_']:
                    if char in cls.LATEX_SPECIAL_CHARS:
                        text = text.replace(char, cls.LATEX_SPECIAL_CHARS[char])
            
            # If it's a question (algorithm), use verbatim-style formatting
            if is_question and '\n' in text:
                # Put algorithm-style text in a small font environment
                lines = text.split('\n')
                formatted_lines = [line.replace('    ', r'\quad ') for line in lines]  # Convert spaces to LaTeX spacing
                text = '\n\n'.join(formatted_lines)
            
            return text
        
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html5lib')
        
        # Handle equation images first (before converting to text)
        for img in soup.find_all('img', class_='equation_image'):
            latex = cls.convert_equation_image(img)
            # Add spaces around the equation to preserve word boundaries
            img.replace_with(f' {latex} ')
        
        # Convert HTML tags to LaTeX
        for tag in soup.find_all('strong') + soup.find_all('b'):
            tag.replace_with(f'\\textbf{{{tag.get_text()}}}')
        
        for tag in soup.find_all('em') + soup.find_all('i'):
            tag.replace_with(f'\\textit{{{tag.get_text()}}}')
        
        for tag in soup.find_all('sub'):
            content = tag.get_text()
            tag.replace_with(f'$_{{{content}}}$')
        
        for tag in soup.find_all('sup'):
            content = tag.get_text()
            tag.replace_with(f'$^{{{content}}}$')
        
        # Get text content - use space as separator to prevent words from running together
        text = soup.get_text(separator=' ')
        
        # Replace non-breaking spaces and other unicode spaces with regular spaces
        text = text.replace('\u00a0', ' ')  # non-breaking space
        text = text.replace('\u2003', ' ')  # em space
        text = text.replace('\u2002', ' ')  # en space
        
        # Clean up whitespace but preserve paragraph breaks
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # Collapse multiple spaces into single space (from missing equations in Canvas export)
        text = re.sub(r'  +', ' ', text)
        text = text.strip()
        
        # Check if this looks like code/algorithm with numbered lines
        # Pattern: "1. ... 2. ... 3. ..." or similar
        if re.search(r'\d+\.\s+', text):
            # Replace numbered lines with actual line breaks for algorithms
            # Match patterns like "2. ", "3. ", etc. but not at the start
            text = re.sub(r'(\d+\.\s+)', r'\n\1', text)
            text = text.strip()  # Remove leading newline
        
        # Convert math expressions with ^ to LaTeX math mode
        # Handle all patterns in a single pass to avoid nested $ signs
        def convert_math_expr(match):
            expr = match.group(0)
            # Already in math mode
            if expr.startswith('$'):
                return expr
            # Parenthesized expression possibly with exponent: (b^k/2) or (b^k/2)^2
            paren_match = re.match(r'\(([^)]*\^[^)]*)\)(\^\d+)?', expr)
            if paren_match:
                inner = paren_match.group(1)
                exp = paren_match.group(2)
                return f'$({inner})' + (f'^{{{exp[1:]}}}' if exp else '') + '$'
            # Simple expression: n^2, b^k, b^k/2
            return f'${expr}$'
        
        # Find all expressions with ^
        text = re.sub(r'\([^)]*\^[^)]*\)(?:\^\d+)?|\w\^[\w/]+', convert_math_expr, text)
        
        # Don't escape text that already contains LaTeX commands
        if '\\' in text or re.search(r'\$.*\$', text):
            # Has LaTeX - only escape &, %, #
            text = text.replace('&', r'\&')
            text = text.replace('%', r'\%')
            text = text.replace('#', r'\#')
        else:
            # No LaTeX - escape problematic special chars
            for char in ['&', '%', '$', '#', '_']:
                if char in cls.LATEX_SPECIAL_CHARS:
                    text = text.replace(char, cls.LATEX_SPECIAL_CHARS[char])
        
        return text


class CanvasQuizParser:
    """Parses Canvas quiz CSV exports."""
    
    def __init__(self, csv_path: str):
        """Initialize parser with CSV file path."""
        self.csv_path = csv_path
        self.df = None
        self.questions = {}  # ItemID -> Question Text mapping
        
    def parse(self) -> None:
        """Parse the CSV file."""
        print(f"Reading CSV file: {self.csv_path}")
        self.df = pd.read_csv(self.csv_path)
        self._extract_questions_from_headers()
    
    def _extract_questions_from_headers(self) -> None:
        """Extract question information from column headers."""
        columns = self.df.columns.tolist()
        
        # Pattern: ItemID (or ItemID.1, ItemID.2, etc.), ItemType, [Question Text], EarnedPoints, Status
        i = 0
        while i < len(columns):
            # Check if this column is ItemID (including renamed versions like ItemID.1)
            if columns[i].startswith('ItemID') and i + 4 < len(columns):
                # Next columns should be: ItemType, Question, EarnedPoints, Status
                item_id_col = i
                item_type_col = i + 1
                question_col = i + 2
                earned_points_col = i + 3
                status_col = i + 4
                
                # Verify the pattern
                if (columns[item_type_col].startswith('ItemType') and
                    columns[earned_points_col].startswith('EarnedPoints') and
                    columns[status_col].startswith('Status')):
                    
                    question_text = columns[question_col]
                    
                    # Store mapping using status column as key (unique identifier)
                    self.questions[status_col] = {
                        'text': question_text,
                        'item_type_col': item_type_col,
                        'question_col': question_col,
                        'earned_points_col': earned_points_col,
                        'status_col': status_col,
                    }
                
                i += 5  # Move to next question block
            else:
                i += 1
    
    def get_student_data(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Extract student data from the CSV.
        
        Args:
            limit: Optional limit on number of students to process
            
        Returns:
            List of dictionaries containing student information
        """
        students = []
        
        # Get only the specified number of rows
        rows_to_process = self.df.head(limit) if limit else self.df
        
        for idx, row in rows_to_process.iterrows():
            name = row['Name']
            student_id = row['ID']
            
            # Extract essay questions that were graded
            questions_answered = []
            
            for status_col, q_info in self.questions.items():
                # Use column name to access the data
                item_type = row[self.df.columns[q_info['item_type_col']]]
                status = row[status_col]
                answer = row[self.df.columns[q_info['question_col']]]
                
                # Only include essay questions that were graded and have an answer
                if (item_type == 'essay' and 
                    status == 'Graded' and 
                    pd.notna(answer) and 
                    str(answer).strip() != ''):
                    
                    questions_answered.append({
                        'question_text': q_info['text'],
                        'answer': answer,
                    })
            
            if questions_answered:  # Only add students who answered questions
                students.append({
                    'name': name,
                    'id': student_id,
                    'questions': questions_answered,
                })
        
        return students


class LaTeXGenerator:
    """Generates LaTeX files from student data."""
    
    def __init__(self, template_path: str, output_dir: str):
        """Initialize generator with template and output directory."""
        self.template_path = template_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(template_path, 'r') as f:
            self.template = f.read()
        
        self.converter = HTMLToLatexConverter()
    
    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitize student name for use as filename."""
        # Remove or replace problematic characters
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        name = name.strip()
        return name
    
    def generate_questions_section(self, questions: List[Dict]) -> str:
        """Generate the questions section of the LaTeX document."""
        sections = []
        
        for i, q in enumerate(questions, 1):
            question_text = self.converter.html_to_latex(q['question_text'], is_question=True)
            answer_text = self.converter.html_to_latex(q['answer'], is_question=False)
            
            # Add line breaks after sentences to help LaTeX with very long paragraphs
            # Only do this for very long single-line answers
            if '\n' not in answer_text and len(answer_text) > 200:
                # Add line breaks after periods to break up long text
                answer_text = re.sub(r'\.\s+', r'. \\\\ ', answer_text)
            
            # Check if question looks like code/algorithm - use small font
            if '\n' in question_text and re.search(r'\d+\.\s+', question_text):
                # Replace newlines with LaTeX line breaks for proper formatting
                algorithm_text = question_text.replace('\n', ' \\\\\n')
                question_section = f"""\\begin{{small}}
{algorithm_text}
\\end{{small}}"""
            else:
                question_section = question_text
            
            section = f"""\\section*{{Question {i}}}

{question_section}

\\vspace{{0.5em}}
\\noindent\\textbf{{Answer:}}

\\begin{{RaggedRight}}
{answer_text}
\\end{{RaggedRight}}

\\vspace{{1em}}
"""
            sections.append(section)
        
        return '\n'.join(sections)
    
    def generate_latex_file(self, student: Dict) -> Path:
        """Generate LaTeX file for a student."""
        # Create filename
        filename = self.sanitize_filename(student['name']) + '.tex'
        filepath = self.output_dir / filename
        
        # Generate questions section
        questions_section = self.generate_questions_section(student['questions'])
        
        # Populate template
        content = self.template.replace('STUDENT_NAME', student['name'])
        content = content.replace('STUDENT_ID', str(student['id']))
        content = content.replace('QUESTIONS_SECTION', questions_section)
        
        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Generated: {filepath}")
        return filepath
    
    def compile_pdf(self, tex_filepath: Path) -> bool:
        """Compile LaTeX file to PDF using pdflatex."""
        try:
            # Run pdflatex twice for proper references
            for _ in range(2):
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', '-output-directory',
                     str(self.output_dir), str(tex_filepath)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            # Check if PDF was created
            pdf_path = tex_filepath.with_suffix('.pdf')
            if pdf_path.exists():
                print(f"Compiled PDF: {pdf_path}")
                
                # Clean up auxiliary files
                for ext in ['.aux', '.log', '.out']:
                    aux_file = tex_filepath.with_suffix(ext)
                    if aux_file.exists():
                        aux_file.unlink()
                
                return True
            else:
                print(f"Warning: PDF compilation failed for {tex_filepath}")
                if result.stderr:
                    print(f"Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"Error: PDF compilation timed out for {tex_filepath}")
            return False
        except FileNotFoundError:
            print("Error: pdflatex not found. Please install LaTeX (e.g., TeX Live or MiKTeX)")
            return False
        except Exception as e:
            print(f"Error compiling PDF: {e}")
            return False


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Convert Canvas quiz CSV to individual student LaTeX/PDF files'
    )
    parser.add_argument(
        '--csv',
        required=True,
        help='Path to Canvas quiz export CSV file'
    )
    parser.add_argument(
        '--output',
        default='./output',
        help='Output directory for generated files (default: ./output)'
    )
    parser.add_argument(
        '--template',
        default='template.tex',
        help='Path to LaTeX template file (default: template.tex)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of students to process (for testing)'
    )
    parser.add_argument(
        '--no-pdf',
        action='store_true',
        help='Skip PDF compilation, only generate .tex files'
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.csv):
        print(f"Error: CSV file not found: {args.csv}")
        sys.exit(1)
    
    if not os.path.exists(args.template):
        print(f"Error: Template file not found: {args.template}")
        sys.exit(1)
    
    try:
        # Parse CSV
        parser = CanvasQuizParser(args.csv)
        parser.parse()
        
        # Get student data
        students = parser.get_student_data(limit=args.limit)
        print(f"\nFound {len(students)} students with essay answers")
        
        if not students:
            print("No students found with graded essay questions.")
            return
        
        # Generate LaTeX files
        generator = LaTeXGenerator(args.template, args.output)
        
        success_count = 0
        pdf_success_count = 0
        
        for student in students:
            try:
                tex_filepath = generator.generate_latex_file(student)
                success_count += 1
                
                # Compile to PDF unless --no-pdf flag is set
                if not args.no_pdf:
                    if generator.compile_pdf(tex_filepath):
                        pdf_success_count += 1
                        
            except Exception as e:
                print(f"Error processing {student['name']}: {e}")
                continue
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  LaTeX files generated: {success_count}/{len(students)}")
        if not args.no_pdf:
            print(f"  PDFs compiled: {pdf_success_count}/{len(students)}")
        print(f"  Output directory: {args.output}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

