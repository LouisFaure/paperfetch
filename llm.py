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
        self.temperature = model_settings.get('temperature', 0.1)

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
        Process papers in batches for summarization and multi-set grading.
        """
        if not papers:
            return {}

        titles = list(papers.keys())
        abstracts = [papers[t]['abstract'] for t in titles]
        
        # 1. Generate Summaries
        print(f"Generating summaries for {len(titles)} papers...")
        summary_prompts = [
            f"<start_of_turn>user\nSummarize the following research abstract into 3-5 concise bullet points. Output only the bullet points.\n\nAbstract: {a}<end_of_turn>\n<start_of_turn>model\n"
            for a in abstracts
        ]
        
        summaries = []
        for i in range(0, len(summary_prompts), self.batch_size):
            batch = summary_prompts[i:i+self.batch_size]
            summaries.extend(self._generate_batch(batch))
            
        # 2. Generate Binary Grades for each Query Set
        query_sets = self.config.get('query_sets', {})
        paper_grades = {title: {} for title in titles}
        
        for set_key, set_info in query_sets.items():
            print(f"Grading papers for set: {set_info['name']}...")
            terms_str = ", ".join(set_info['terms'])
            grading_prompts = [
                f"<start_of_turn>user\nDoes this paper ACTUALLY USE or STUDY any of these: {terms_str}?\n\nAnswer 1 if the paper:\n- Uses this METHOD/TECHNOLOGY to generate or analyze data\n- Studies this TISSUE/DISEASE as the subject of research\n- Investigates this CONCEPT/PHENOMENON as part of the study\n\nAnswer 0 if:\n- Only mentioned as background, related work, or future direction\n- Individual words match but NOT the complete phrase (e.g., 'Spatial' alone does NOT match 'Spatial Transcriptomic Assay')\n- The concept is tangentially related but not actually investigated\n\nOutput ONLY 0 or 1.\n\nAbstract: {a}<end_of_turn>\n<start_of_turn>model\n"
                for a in abstracts
            ]
            
            set_responses = []
            for i in range(0, len(grading_prompts), self.batch_size):
                batch = grading_prompts[i:i+self.batch_size]
                set_responses.extend(self._generate_batch(batch))
            
            for title, response in zip(titles, set_responses):
                # Simple extraction of 0 or 1
                match = re.search(r'[01]', response)
                grade = int(match.group(0)) if match else 0
                paper_grades[title][set_key] = grade

        # 3. Combine results
        results = {}
        for i, title in enumerate(titles):
            # Parse summary into list
            points = [p.strip('- ').strip('* ') for p in summaries[i].split('\n') if p.strip()]
            
            # Calculate final score
            final_score = 0
            grades = paper_grades[title]
            for set_key, grade in grades.items():
                multiplier = query_sets[set_key].get('multiplier', 1.0)
                final_score += grade * multiplier
            
            results[title] = {
                'summary': points,
                'grades': grades,
                'final_score': final_score,
                'url': papers[title]['url'],
                'journal': papers[title].get('journal')
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
