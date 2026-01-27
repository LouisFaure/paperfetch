#!/bin/bash
#SBATCH --job-name=paperfetch_weekly
#SBATCH --output=/home/faurel1/tools/paperfetch/logs/%x_%j.out
#SBATCH --error=/home/faurel1/tools/paperfetch/logs/%x_%j.err
#SBATCH --time=00:15:00
#SBATCH --partition=componc_gpu_preemp
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G

# Run paperfetch
cd /home/faurel1/tools/paperfetch
uv run main.py --local

# Resubmit this same script to run in 7 days
sbatch --begin=now+7days "$0"
