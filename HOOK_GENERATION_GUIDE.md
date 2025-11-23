# AI Hook Generation Guide

## Overview

This system generates personalized "hooks" for each lead using OpenAI's GPT-4o model. Hooks are designed to establish credibility and create need by highlighting how AI is changing recruitment for their specific role.

## Features

### 1. **Automated Hook Generation**
- Uses GPT-4o to generate personalized hooks for each lead
- Hooks are based on: Name, Credentials, Title, Current Role, and Company
- Each hook is 2-3 short sentences, pithy and direct
- Challenges current positioning and points to elevated value
- Cites how AI is changing recruitment for their role
- Ends with Mobiusengine.ai reference

### 2. **Command-Line Utility**
Generate hooks for all leads without hooks:
```bash
python3 generate_hooks.py <db_password>
```

Generate hooks for specific number of leads:
```bash
python3 generate_hooks.py <db_password> --limit 10
```

Regenerate hooks for all leads (including those with existing hooks):
```bash
python3 generate_hooks.py <db_password> --regenerate
```

### 3. **Web Interface**
- **Dashboard**: Shows count of AI hooks generated
- **Leads Page**: 
  - Displays hook preview for each lead
  - "Generate Hook" button for individual lead hook generation
  - Real-time updates when hooks are generated

### 4. **API Endpoints**

#### Generate Hook for Single Lead
```
POST /api/generate-hook/<lead_id>
```
Response:
```json
{
  "success": true,
  "hook": "Generated hook text..."
}
```

#### Generate Hooks for All Leads
```
POST /api/generate-all-hooks
```
Response:
```json
{
  "success": true,
  "total": 293,
  "generated": 293,
  "failed": 0
}
```

## Hook Format

Each hook follows this structure:

1. **Challenge Statement**: "Many firms still treat [role] as..."
2. **Value Proposition**: "Your expertise in [credentials/skills]..."
3. **Call to Action**: "Mobiusengine.ai can help you land your next role"

### Example Hooks

**Example 1:**
> Many firms still treat sales enablement as a routine function, but your proven leadership in B2B sales, customer relationship management, and negotiations sets you apart as a true innovator in driving business growth. As a Director of Direct Sales, Channel Sales, and Business Development for Infrastructure Solutions at PerfectVision, you bring unparalleled value in an era where AI is reshaping recruitment strategies. Mobiusengine.ai can help you land your next role in this evolving landscape.

**Example 2:**
> In today's market, many firms still treat roles like Chief Hydr8tion Officer as standard, overlooking unique creators like you who founded HYDR8, honoring heroes with every bottle. Your leadership in supporting Veterans and First Responders sets you apart in a landscape where AI is reshaping recruitment. Mobiusengine.ai can help you land your next role.

## Database Schema

The `leads` table includes:
- `hook` (TEXT): The generated hook text
- `hook_generated_at` (TIMESTAMP): When the hook was generated
- Index on `hook` column for fast queries

## Configuration

### OpenAI API Key
Stored in GCP Secret Manager:
- **Secret Name**: `openai-api-key`
- **Project**: `jobs-data-linkedin`
- **Access**: Retrieved automatically by the application

### Model Settings
- **Model**: `gpt-4o`
- **Temperature**: 0.7 (balanced creativity)
- **Max Tokens**: 200 (ensures concise output)

## Usage Statistics

- **Total Leads**: 295
- **Hooks Generated**: ~293 (in progress)
- **Success Rate**: ~100%
- **Average Hook Length**: 300-500 characters

## Next Steps

1. ✅ Generate hooks for all 295 leads
2. Review hook quality and adjust prompt if needed
3. Add bulk export functionality (CSV with hooks)
4. Add filtering by hook status (has hook / no hook)
5. Add hook regeneration for specific leads
6. Consider A/B testing different hook styles

## Technical Details

### Dependencies
- `openai==1.54.0` - OpenAI API client
- `google-cloud-secret-manager==2.21.1` - GCP Secret Manager
- `psycopg2-binary` - PostgreSQL database
- `Flask` - Web framework

### Files
- `generate_hooks.py` - Command-line utility
- `add_hook_column.sql` - Database schema update
- `main.py` - Flask app with API endpoints
- `templates/leads.html` - Web UI for viewing/generating hooks
- `templates/index.html` - Dashboard with hook statistics

## Troubleshooting

### Issue: "Illegal header value" error
**Solution**: Make sure to strip whitespace from API key when retrieving from Secret Manager:
```python
return response.payload.data.decode("UTF-8").strip()
```

### Issue: Hooks are too long
**Solution**: Adjust the prompt to emphasize "2-3 short sentences" or reduce `max_tokens` parameter.

### Issue: Hooks don't mention Mobiusengine.ai
**Solution**: The prompt explicitly requires this. If missing, regenerate the hook.

## Support

For issues or questions, contact the development team or check the project repository:
- **Repository**: https://github.com/mobius-engine/personalizedcampaign
- **GCP Project**: jobs-data-linkedin

