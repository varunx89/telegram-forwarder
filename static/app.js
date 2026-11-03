document.addEventListener('DOMContentLoaded', () => {
    // Wizard Elements
    const stepPhone = document.getElementById('step-phone');
    const stepCode = document.getElementById('step-code');
    const stepPassword = document.getElementById('step-password');
    
    const phoneInput = document.getElementById('phone-input');
    const codeInput = document.getElementById('code-input');
    const passwordInput = document.getElementById('password-input');
    
    const btnSendCode = document.getElementById('btn-send-code');
    const btnVerifyCode = document.getElementById('btn-verify-code');
    const btnSubmitPassword = document.getElementById('btn-submit-password');
    const btnBackToPhone = document.getElementById('btn-back-to-phone');
    const btnLogout = document.getElementById('btn-logout');
    const btnCopySession = document.getElementById('btn-copy-session');
    const btnRefreshLogs = document.getElementById('btn-refresh-logs');
    
    const wizardFeedback = document.getElementById('wizard-feedback');
    const loginWizardView = document.getElementById('login-wizard-view');
    const accountDetailsView = document.getElementById('account-details-view');
    const connectionBadge = document.getElementById('connection-badge');
    const sessionStringInput = document.getElementById('session-string-input');
    const logsBody = document.getElementById('logs-body');

    function showFeedback(message, type = 'danger') {
        if (!wizardFeedback) return;
        wizardFeedback.className = `alert alert-${type} mt-3`;
        wizardFeedback.innerHTML = message;
        wizardFeedback.classList.remove('hidden');
    }

    function clearFeedback() {
        if (!wizardFeedback) return;
        wizardFeedback.classList.add('hidden');
        wizardFeedback.innerHTML = '';
    }

    function setStep(step) {
        clearFeedback();
        if (stepPhone) stepPhone.classList.add('hidden');
        if (stepCode) stepCode.classList.add('hidden');
        if (stepPassword) stepPassword.classList.add('hidden');

        if (step === 'phone' && stepPhone) stepPhone.classList.remove('hidden');
        if (step === 'code' && stepCode) {
            stepCode.classList.remove('hidden');
            if (codeInput) codeInput.focus();
        }
        if (step === 'password' && stepPassword) {
            stepPassword.classList.remove('hidden');
            if (passwordInput) passwordInput.focus();
        }
    }

    // 1. Request Code
    if (btnSendCode) {
        btnSendCode.addEventListener('click', async () => {
            const phone = phoneInput ? phoneInput.value.trim() : '';
            if (!phone) {
                showFeedback('Please enter your phone number including country code (e.g. +1234567890).', 'warning');
                return;
            }

            btnSendCode.disabled = true;
            btnSendCode.innerText = 'Sending...';
            clearFeedback();

            try {
                const res = await fetch('/api/auth/send-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone })
                });
                const data = await res.json();

                if (data.success) {
                    showFeedback(data.message, 'success');
                    setStep('code');
                } else {
                    showFeedback(data.error || 'Failed to send verification code.', 'danger');
                }
            } catch (err) {
                showFeedback('Network error while requesting code: ' + err.message, 'danger');
            } finally {
                btnSendCode.disabled = false;
                btnSendCode.innerText = 'Request Code';
            }
        });
    }

    // Back to Phone
    if (btnBackToPhone) {
        btnBackToPhone.addEventListener('click', (e) => {
            e.preventDefault();
            setStep('phone');
        });
    }

    // 2. Verify Code
    if (btnVerifyCode) {
        btnVerifyCode.addEventListener('click', async () => {
            const code = codeInput ? codeInput.value.trim() : '';
            if (!code) {
                showFeedback('Please enter the verification code received on Telegram.', 'warning');
                return;
            }

            btnVerifyCode.disabled = true;
            btnVerifyCode.innerText = 'Verifying...';
            clearFeedback();

            try {
                const res = await fetch('/api/auth/verify-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code })
                });
                const data = await res.json();

                if (data.success) {
                    showFeedback('Logged in successfully!', 'success');
                    setTimeout(() => window.location.reload(), 1000);
                } else if (data.requires_password) {
                    showFeedback(data.message, 'warning');
                    setStep('password');
                } else {
                    showFeedback(data.error || 'Verification failed.', 'danger');
                }
            } catch (err) {
                showFeedback('Network error while verifying code: ' + err.message, 'danger');
            } finally {
                btnVerifyCode.disabled = false;
                btnVerifyCode.innerText = 'Verify Code';
            }
        });
    }

    // 3. Submit 2FA Password
    if (btnSubmitPassword) {
        btnSubmitPassword.addEventListener('click', async () => {
            const password = passwordInput ? passwordInput.value : '';
            if (!password) {
                showFeedback('Please enter your 2FA password.', 'warning');
                return;
            }

            btnSubmitPassword.disabled = true;
            btnSubmitPassword.innerText = 'Submitting...';
            clearFeedback();

            try {
                const res = await fetch('/api/auth/submit-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const data = await res.json();

                if (data.success) {
                    showFeedback('2FA verified successfully! Reloading...', 'success');
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    showFeedback(data.error || 'Invalid 2FA password.', 'danger');
                }
            } catch (err) {
                showFeedback('Network error while submitting 2FA: ' + err.message, 'danger');
            } finally {
                btnSubmitPassword.disabled = false;
                btnSubmitPassword.innerText = 'Submit 2FA';
            }
        });
    }

    // 4. Logout / Disconnect
    if (btnLogout) {
        btnLogout.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to disconnect this Telegram account session?')) {
                return;
            }
            
            btnLogout.disabled = true;
            btnLogout.innerText = 'Disconnecting...';
            
            try {
                const res = await fetch('/api/auth/logout', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    window.location.reload();
                } else {
                    alert('Logout error: ' + (data.error || 'unknown'));
                }
            } catch (err) {
                alert('Network error: ' + err.message);
            } finally {
                btnLogout.disabled = false;
                btnLogout.innerText = 'Disconnect Account';
            }
        });
    }
});
