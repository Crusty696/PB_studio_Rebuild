# PB Studio Support

Get help with PB Studio installation, configuration, and usage.

## Quick Links

- 📚 [User Documentation](user/)
- 🔧 [Troubleshooting Guide](user/troubleshooting.md)
- ❓ [FAQ](user/faq.md)
- 📥 [Installation Guide](user/INSTALLATION_GUIDE.md)
- 🐛 [Report a Bug](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=bug_report.yml)
- 💡 [Request a Feature](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=feature_request.yml)
- 🆘 [Get Support](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=support_request.yml)

## Support Channels

### GitHub Issues (Primary Support)

For bug reports, feature requests, and technical support:

**[Create a New Issue](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new/choose)**

Select the appropriate template:
- **Bug Report**: Something isn't working as expected
- **Feature Request**: Suggest a new feature or enhancement
- **Support Request**: Get help with installation or usage

**Response Times:**
- Acknowledgment: Within 24 hours
- Critical bugs: 48 hours
- High priority: 1 week
- Medium/Low: Best effort

### GitHub Discussions

For general questions, community discussions, and ideas:

**[Join the Discussion](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/discussions)**

Great for:
- How-to questions
- Workflow tips and tricks
- Community support
- Feature ideas and brainstorming
- Showcase your work

### Email Support

For sensitive issues or private support:
- **Email**: support@pbstudio.example *(update with actual email)*

Use email for:
- Security vulnerability disclosure
- Private/confidential issues
- Business inquiries
- Partnership opportunities

## Before You Submit

### Check Existing Resources

Before creating a support request, please check:

1. **[Troubleshooting Guide](user/troubleshooting.md)** - Common issues and solutions
2. **[FAQ](user/faq.md)** - Frequently asked questions
3. **[Existing Issues](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues)** - Your issue might already be reported
4. **[Discussions](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/discussions)** - Community Q&A

### Gather Information

When reporting an issue, please have ready:

- **PB Studio version** (Help → About)
- **Operating System** (Windows 11, Ubuntu 22.04, etc.)
- **Python version** (`python --version`)
- **GPU information** (if applicable, run `nvidia-smi`)
- **Error logs** from `logs/pb_studio.log`
- **Steps to reproduce** the issue

## Common Issues

### Installation Problems

**Issue**: Dependencies won't install
```bash
# Solution: Use a fresh virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

**Issue**: GPU not detected
```bash
# Check CUDA installation
nvidia-smi

# Verify PyTorch can see GPU
python -c "import torch; print(torch.cuda.is_available())"
```

**Issue**: FFmpeg not found
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org) and add to PATH
- **Linux**: `sudo apt install ffmpeg`
- **Mac**: `brew install ffmpeg`

See [Troubleshooting Guide](user/troubleshooting.md) for more solutions.

### Performance Issues

**Slow processing**:
1. Enable GPU mode in settings
2. Check GPU utilization with `nvidia-smi`
3. Close other GPU-intensive applications
4. Update GPU drivers

**Out of memory errors**:
1. Reduce video resolution
2. Enable memory optimization in settings
3. Lower batch size in configuration
4. Try CPU mode for very large files

### Application Issues

**Won't start**:
1. Check logs: `logs/pb_studio.log`
2. Verify database: `python -c "from database.manager import DatabaseManager; DatabaseManager('pb_studio.db').test_connection()"`
3. Try resetting database (backup first): `mv pb_studio.db pb_studio.db.backup`

**UI freezes or crashes**:
1. Save your work frequently
2. Restart the application
3. Check available RAM and disk space
4. Report persistent crashes with logs

## Getting Help

### Community Support

The PB Studio community is active and helpful! Before creating an issue, try:

1. **[Search Discussions](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/discussions)** - Ask questions, share tips
2. **[Check Issues](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues)** - Browse known issues and solutions
3. **Join Community Chat** *(add Discord/Slack link if available)*

### Professional Support

For organizations, enterprises, or users needing priority support:

- Contact: support@pbstudio.example *(update with actual email)*
- Available services:
  - Priority technical support
  - Custom integration assistance
  - Training and onboarding
  - Performance optimization consulting

## Contributing

Help improve PB Studio and support the community:

- **Report bugs** with detailed reproduction steps
- **Suggest features** with clear use cases
- **Improve documentation** via pull requests
- **Help others** in discussions
- **Share your work** and workflows

See [CONTRIBUTING.md](../CONTRIBUTING.md) *(create if needed)* for guidelines.

## Security

If you discover a security vulnerability, please:

1. **Do NOT** create a public GitHub issue
2. **Email** security@pbstudio.example *(update with actual email)*
3. Include:
   - Vulnerability description
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if you have one)

We'll respond within 48 hours and work with you on disclosure.

## Support Priority

### Critical (Immediate Response)
- Application crashes on startup for all users
- Data loss or corruption
- Security vulnerabilities
- Complete feature failure affecting production use

### High (48 Hours)
- Major features not working
- Significant performance degradation
- Workarounds exist but impact productivity
- Affects multiple users

### Medium (1 Week)
- Minor features not working
- Cosmetic issues
- Workarounds available
- Affects some users

### Low (Best Effort)
- Enhancement requests
- Nice-to-have features
- Documentation improvements
- Questions answered by existing docs

## Feedback

We value your feedback! Let us know:

- What's working well
- What could be improved
- Features you'd like to see
- Documentation gaps
- Your use cases and workflows

**Feedback Form**: *(add form link if available)*
**Community Discussions**: [Share Your Thoughts](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/discussions)

---

## Resources

### Documentation
- [User Guide](user/README.md)
- [Getting Started](user/getting_started.md)
- [Beat Sync Workflow](user/beat_sync_workflow.md)
- [Troubleshooting](user/troubleshooting.md)
- [FAQ](user/faq.md)
- [Keyboard Shortcuts](user/keyboard_shortcuts.md)

### Technical
- [Installation Guide](user/INSTALLATION_GUIDE.md)
- [Production Configuration](PRODUCTION_CONFIG.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Support Playbook](SUPPORT_PLAYBOOK.md) *(for support team)*

### Community
- [GitHub Repository](https://github.com/YOUR_USERNAME/PB_studio_Rebuild)
- [Issue Tracker](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues)
- [Discussions](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/discussions)
- [Releases](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/releases)

---

**Need immediate help?** Create a [Support Request](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=support_request.yml)

**Found a bug?** Submit a [Bug Report](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=bug_report.yml)

**Have an idea?** Share a [Feature Request](https://github.com/YOUR_USERNAME/PB_studio_Rebuild/issues/new?template=feature_request.yml)

---

*Last Updated: 2026-04-07*
