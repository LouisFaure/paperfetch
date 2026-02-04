import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import re
import asyncio

class GemmaProcessor:
    def __init__(self, config):
        self.config = config
        model_settings = config.get('model', {})
        model_name = model_settings.get('name', "google/gemma-3-1b-it")
        print(f"Loading {model_name}...")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "left" # Better for batch generation
            
        # Load model
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        
        self.batch_size = model_settings.get('batch_size', 8)
        self.max_new_tokens = model_settings.get('max_new_tokens', 150)
        self.device = self.model.device
        self.temperature = model_settings.get('temperature', 1.0)

    def _generate_batch(self, prompts):
        inputs = self.tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                do_sample=True if self.temperature > 0 else False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        
        input_len = inputs['input_ids'].shape[1]
        responses = self.tokenizer.batch_decode(outputs[:, input_len:], skip_special_tokens=True)
        return [r.strip() for r in responses]

    def process_papers(self, papers):
        """
        Process papers in batches: first grade them all, then summarize only those passing the threshold.
        """
        if not papers:
            return {}

        titles = list(papers.keys())
        abstracts = [papers[t]['abstract'] for t in titles]
        
        # 1. Generate Binary Grades for each Query Set
        query_sets = self.config.get('query_sets', {})
        paper_grades = {title: {} for title in titles}
        
        for set_key, set_info in query_sets.items():
            print(f"Grading papers for set: {set_info['name']}...")
            question = set_info['question']
            grading_prompts = [
                f"{question}\n\nAnswer 1 if Yes and 0 if No.\n\nOutput ONLY 0 or 1.\n\nAbstract: {a}\n\n"
                for a in abstracts
            ]
            
            set_responses = []
            for i in range(0, len(grading_prompts), self.batch_size):
                batch = grading_prompts[i:i+self.batch_size]
                set_responses.extend(self._generate_batch(batch))
            
            for idx, (title, response) in enumerate(zip(titles, set_responses)):
                # Extract the first standalone 0 or 1 from the response
                clean_response = response.strip()
                match = re.search(r'\b([01])\b', clean_response)
                if match:
                    grade = int(match.group(1))
                else:
                    # Retry
                    grade = 0
                    for attempt in range(3):
                        print(f"Retrying grading for {title} in set {set_key}, attempt {attempt+1}")
                        retry_responses = self._generate_batch([grading_prompts[idx]])
                        retry_response = retry_responses[0] if retry_responses else ""
                        match_retry = re.search(r'\b([01])\b', retry_response.strip())
                        if match_retry:
                            grade = int(match_retry.group(1))
                            break
                    else:
                        print(f"Failed grading for {title}")
                paper_grades[title][set_key] = grade

        # 2. Calculate scores and filter for summarization
        min_score = self.config.get('slack', {}).get('min_score', 1.0)
        passing_titles = []
        final_scores = {}
        
        for title in titles:
            score = 0
            grades = paper_grades[title]
            for set_key, grade in grades.items():
                multiplier = query_sets[set_key].get('multiplier', 1.0)
                score += grade * multiplier
            final_scores[title] = score
            if score >= min_score:
                passing_titles.append(title)
        
        print(f"Found {len(passing_titles)} papers passing threshold (>= {min_score}) out of {len(titles)}")

        # 3. Generate Summaries for passing papers ONLY
        summaries = {title: [] for title in titles}
        if passing_titles:
            print(f"Generating summaries for {len(passing_titles)} papers...")
            passing_abstracts = [papers[t]['abstract'] for t in passing_titles]
            summary_prompts = [
                f"<start_of_turn>user\nSummarize the following research abstract into 3-5 concise bullet points. Output only the bullet points.\n\nAbstract: {a}<end_of_turn>\n<start_of_turn>model\n"
                for a in passing_abstracts
            ]
            
            passing_summaries = []
            for i in range(0, len(summary_prompts), self.batch_size):
                batch = summary_prompts[i:i+self.batch_size]
                passing_summaries.extend(self._generate_batch(batch))
            
            for title, raw_summary in zip(passing_titles, passing_summaries):
                points = [p.strip('- ').strip('* ') for p in raw_summary.split('\n') if p.strip()]
                summaries[title] = points

        # 4. Combine results
        results = {}
        for title in titles:
            results[title] = {
                'summary': summaries[title],
                'grades': paper_grades[title],
                'final_score': final_scores[title],
                'url': papers[title]['url'],
                'journal': papers[title].get('journal'),
                'abstract': papers[title].get('abstract', '') # Keep abstract for md file
            }
            
        return results

async def process_papers_with_llm(papers, config):
    """
    Async wrapper for GemmaProcessor.
    """
    # Create processor and process papers in a separate thread to avoid blocking event loop
    def _run():
        processor = GemmaProcessor(config)
        return processor.process_papers(papers)
    
    return await asyncio.to_thread(_run)
