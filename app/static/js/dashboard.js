<script>
    let currentData = null;
    let allTransactions = [];

    function switchTab(tabName) {
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));

        document.getElementById(tabName).classList.add('active');

        const clickedTab = Array.from(document.querySelectorAll('.nav-tab')).find(tab =>
            tab.getAttribute('onclick').includes(tabName)
        );
        if (clickedTab) clickedTab.classList.add('active');
    }

    function loadSampleData() {
        showStatus('Loading sample data...', 'info');

        fetch('/api/load-sample-data', {method: 'POST'})
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showStatus(' Sample data loaded!', 'success');
                    updateDashboard(data.data);
                    setTimeout(() => switchTab('dashboard'), 1500);
                } else {
                    showStatus(' Error: ' + data.message, 'error');
                }
            })
            .catch(error => showStatus(' Error: ' + error, 'error'));
    }

    document.getElementById('fileInput').addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;

        const fileName = file.name.toLowerCase();
        const fileExtension = fileName.split('.').pop();

        let endpoint = '/api/upload-csv';
        let fileType = 'CSV';

        if (fileExtension === 'xlsx' || fileExtension === 'xls') {
            endpoint = '/api/upload-excel';
            fileType = 'Excel';
        } else if (fileExtension !== 'csv') {
            showStatus(' Unsupported file type', 'error');
            return;
        }

        showStatus(`Uploading ${fileType} file...`, 'info');

        const formData = new FormData();
        formData.append('file', file);

        fetch(endpoint, {method: 'POST', body: formData})
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showStatus(' ' + data.message, 'success');
                    updateDashboard(data.data);
                    setTimeout(() => switchTab('dashboard'), 2000);
                } else {
                    showStatus(' Error: ' + data.message, 'error');
                }
            })
            .catch(error => showStatus(' Upload failed: ' + error, 'error'));
    });

    function showStatus(message, type) {
        const statusDiv = document.getElementById('uploadStatus');
        statusDiv.style.display = 'block';
        statusDiv.textContent = message;
        statusDiv.className = 'status-message ' + type;
    }

    function loadTemporalInsights() {
        fetch('/api/insights/temporal')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    renderTemporalInsights(data.insights);
                }
            })
            .catch(error => {
                console.log('Temporal insights not available:', error);
            });
    }

    function renderTemporalInsights(insights) {
        const container = document.getElementById('trendsContent');
        if (!container || !insights) return;

        let html = '';

        if (insights.data_quality && insights.data_quality.warning) {
            html += `
            <div style="background: rgba(255, 192, 30, 0.15); border: 1px solid var(--accent-yellow);
                        border-radius: 8px; padding: 12px 16px; margin-bottom: 20px;">
                <strong style="color: var(--accent-yellow);">⚠ ${insights.data_quality.warning}</strong>
            </div>
        `;
        }

        if (insights.fastest_growing) {
            const fg = insights.fastest_growing;
            html += `
            <div style="background: var(--bg-secondary); border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                <div style="color: var(--text-muted); font-size: 12px; margin-bottom: 8px;">
                    FASTEST GROWING CATEGORY
                </div>
                <div style="color: var(--accent-green); font-size: 24px; font-weight: 700; margin-bottom: 8px;">
                    ${fg.category} +${fg.change_percent.toFixed(0)}%
                </div>
                <div style="color: var(--text-secondary); font-size: 14px;">
                    ₹${fg.previous_spend.toLocaleString('en-IN', {maximumFractionDigits: 0})} →
                    ₹${fg.current_spend.toLocaleString('en-IN', {maximumFractionDigits: 0})}
                </div>
            </div>
        `;
        }

        if (insights.acceleration_flags && insights.acceleration_flags.length > 0) {
            html += `
            <div style="margin-bottom: 20px;">
                <div style="color: var(--text-primary); font-size: 16px; font-weight: 600; margin-bottom: 12px;">
                    ⚡ Accelerating Spending
                </div>
        `;

            insights.acceleration_flags.forEach(flag => {
                html += `
                <div style="background: rgba(255, 153, 102, 0.1); border-left: 3px solid var(--accent-orange);
                            padding: 12px 16px; border-radius: 6px; margin-bottom: 8px;">
                    <div style="color: var(--text-primary); font-weight: 600; margin-bottom: 4px;">
                        ${flag.category}
                    </div>
                    <div style="color: var(--text-secondary); font-size: 13px;">
                        ${flag.explanation}
                    </div>
                    <div style="color: var(--text-muted); font-size: 12px; margin-top: 4px;">
                        Current: ₹${flag.current_spend.toLocaleString('en-IN', {maximumFractionDigits: 0})} |
                        Avg: ₹${flag.trailing_avg.toLocaleString('en-IN', {maximumFractionDigits: 0})}
                    </div>
                </div>
            `;
            });

            html += `</div>`;
        }

        if (insights.mom_changes && insights.mom_changes.length > 0) {
            html += `
            <div>
                <div style="color: var(--text-primary); font-size: 16px; font-weight: 600; margin-bottom: 12px;">
                    📊 Month-over-Month Changes
                </div>
        `;

            const topChanges = insights.mom_changes.slice(0, 5);

            topChanges.forEach(change => {
                const isIncrease = change.change_amount > 0;
                const color = isIncrease ? 'var(--accent-orange)' : 'var(--accent-green)';
                const arrow = isIncrease ? '↑' : '↓';

                html += `
                <div style="display: flex; justify-content: space-between; align-items: center;
                            padding: 12px 0; border-bottom: 1px solid var(--border);">
                    <div>
                        <div style="color: var(--text-primary); font-weight: 600;">
                            ${change.category}
                        </div>
                        <div style="color: var(--text-muted); font-size: 13px;">
                            ${change.previous_month} → ${change.current_month}
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: ${color}; font-size: 18px; font-weight: 700;">
                            ${arrow} ${Math.abs(change.change_percent).toFixed(0)}%
                        </div>
                        <div style="color: var(--text-muted); font-size: 12px;">
                            ${isIncrease ? '+' : ''}₹${change.change_amount.toLocaleString('en-IN', {maximumFractionDigits: 0})}
                        </div>
                    </div>
                </div>
            `;
            });

            html += `</div>`;
        }

        container.innerHTML = html;
    }

    function updateDashboard(data) {
        document.getElementById('noDataState').classList.add('hidden');
        document.getElementById('dashboardContent').classList.remove('hidden');

        if (data.metrics) {
            document.getElementById('totalSpend').textContent = data.metrics.total_monthly_spend.value;
            document.getElementById('totalTransactions').textContent = data.metrics.total_monthly_spend.sublabel;
            document.getElementById('fixedExpenses').textContent = data.metrics.fixed_expenses.value;
            document.getElementById('fixedCategories').textContent = data.metrics.fixed_expenses.sublabel;
            document.getElementById('variableExpenses').textContent = data.metrics.variable_expenses.value;
            document.getElementById('variableCategories').textContent = data.metrics.variable_expenses.sublabel;
            document.getElementById('momDrift').textContent = data.metrics.mom_drift.value;
            document.getElementById('momTrend').textContent = data.metrics.mom_drift.sublabel;
        }

        if (data.category_breakdown) {
            const tbody = document.getElementById('categoryTableBody');
            tbody.innerHTML = '';

            data.category_breakdown.forEach(cat => {
                const row = tbody.insertRow();
                row.innerHTML = `
                        <td><strong>${cat.category}</strong></td>
                        <td><span class="badge ${cat.type === 'Fixed' ? 'badge-fixed' : 'badge-variable'}">${cat.type}</span></td>
                        <td>${cat.monthly_avg}</td>
                        <td>${cat.percentage}</td>
                    `;
            });

            const labels = data.category_breakdown.map(c => c.category);
            const values = data.category_breakdown.map(c => parseFloat(c.monthly_avg.replace(/[₹,]/g, '')));

            const pieData = [{
                values: values,
                labels: labels,
                type: 'pie',
                marker: {
                    colors: ['#00b8a3', '#ffc01e', '#ff9966', '#ef4743', '#4a90e2', '#9b59b6', '#2ecc71', '#e74c3c']
                },
                textfont: {color: '#ffffff'}
            }];

            const pieLayout = {
                margin: {l: 0, r: 0, t: 0, b: 0},
                showlegend: true,
                paper_bgcolor: '#2d2d2d',
                plot_bgcolor: '#2d2d2d',
                font: {color: '#ffffff'},
                legend: {font: {color: '#a3a3a3'}}
            };

            Plotly.newPlot('pieChart', pieData, pieLayout, {responsive: true});
        }

        if (data.anomalies && data.anomalies.length > 0) {
            const anomalyList = document.getElementById('anomalyList');
            anomalyList.innerHTML = '';

            data.anomalies.forEach(anom => {
                const div = document.createElement('div');
                div.className = 'anomaly-item';
                div.innerHTML = `
                        <div class="anomaly-header">${anom.category}</div>
                        <div class="anomaly-amount">${anom.amount}</div>
                        <div class="anomaly-explanation">${anom.explanation}</div>
                `;
                anomalyList.appendChild(div);
            });
        }

        if (data.action_items && data.action_items.length > 0) {
            const actionsList = document.getElementById('actionItemsList');
            actionsList.innerHTML = '';

            data.action_items.forEach(action => {
                const div = document.createElement('div');
                div.className = 'action-item';
                div.innerHTML = `
                        <span class="action-priority ${action.priority_class}">${action.priority}</span>
                        <div class="action-title">${action.action}</div>
                        <div class="action-impact">${action.impact}</div>
                        <div class="action-timeline">Timeline: ${action.timeline}</div>
                    `;
                actionsList.appendChild(div);
            });
        }

        // Enable drill-down
        setTimeout(() => {
            fetchTransactions();
            makeCategoryTableClickable();
            makePieChartClickable();

            const tableContainer = document.querySelector('.table-container');
            if (tableContainer && !document.querySelector('.clickable-hint')) {
                const hint = document.createElement('div');
                hint.className = 'clickable-hint';
                hint.textContent = 'Click any category to view detailed transactions';
                tableContainer.appendChild(hint);
            }
        }, 500);

        // Load temporal insights
        setTimeout(() => {
            loadTemporalInsights();
        }, 1000);

        // Load subscriptions
        setTimeout(() => {
            loadSubscriptions();
        }, 1500);
    }

    function loadSubscriptions() {
        fetch('/api/subscriptions/audit')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    renderSubscriptions(data.report);
                }
            })
            .catch(error => {
                console.log('Subscriptions not available:', error);
                document.getElementById('subscriptionsList').innerHTML =
                    '<p style="color: var(--text-muted);">No subscriptions detected</p>';
            });
    }

    function renderSubscriptions(report) {
        const container = document.getElementById('subscriptionsList');

        if (!report.subscriptions || report.subscriptions.length === 0) {
            container.innerHTML = '<p style="color: var(--text-muted);">No recurring subscriptions detected</p>';
            return;
        }

        let html = `
        <div style="background: var(--bg-secondary); padding: 16px; border-radius: 8px; margin-bottom: 20px;">
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px;">
                <div>
                    <div style="color: var(--text-muted); font-size: 12px;">TOTAL SUBSCRIPTIONS</div>
                    <div style="color: var(--text-primary); font-size: 24px; font-weight: 700;">
                        ${report.summary.total_subscriptions}
                    </div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 12px;">EST. MONTHLY COST</div>
                    <div style="color: var(--accent-orange); font-size: 24px; font-weight: 700;">
                        ₹${report.summary.total_monthly_cost.toLocaleString('en-IN', {maximumFractionDigits: 0})}
                    </div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 12px;">COST INCREASES</div>
                    <div style="color: var(--accent-red); font-size: 24px; font-weight: 700;">
                        ${report.summary.increasing_cost || 0}
                    </div>
                </div>
            </div>
        </div>
    `;

        report.subscriptions.forEach(sub => {
            const flagColor = sub.flags.includes('cost_increase') ? 'var(--accent-red)' :
                sub.flags.includes('long_running') ? 'var(--accent-yellow)' : 'var(--accent-green)';

            html += `
            <div style="background: var(--bg-secondary); border: 1px solid var(--border);
                        border-radius: 8px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
                    <div>
                        <div style="color: var(--text-primary); font-weight: 600; font-size: 16px;">
                            ${sub.entity}
                        </div>
                        <div style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">
                            ${sub.category} • ${sub.frequency}
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="color: ${flagColor}; font-size: 20px; font-weight: 700;">
                            ₹${sub.avg_amount.toLocaleString('en-IN', {maximumFractionDigits: 0})}
                        </div>
                        <div style="color: var(--text-muted); font-size: 12px;">
                            ${sub.occurrences} charges
                        </div>
                    </div>
                </div>
                <div style="color: var(--text-secondary); font-size: 14px; line-height: 1.5;">
                    ${sub.explanation}
                </div>
                ${sub.flags.length > 0 ? `
                    <div style="margin-top: 8px; display: flex; gap: 8px;">
                        ${sub.flags.map(flag => `
                            <span style="background: rgba(239, 71, 67, 0.15); color: var(--accent-red);
                                         padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">
                                ${flag.replace('_', ' ').toUpperCase()}
                            </span>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;
        });

        container.innerHTML = html;
    }

    // ========== MODAL FUNCTIONS ==========

    function showCategoryTransactions(categoryName) {
        if (!allTransactions || allTransactions.length === 0) {
            console.log('No transactions loaded yet');
            return;
        }

        const categoryTxns = allTransactions.filter(txn => txn.category === categoryName);

        if (categoryTxns.length === 0) {
            alert(`No transactions found for ${categoryName}`);
            return;
        }

        const totalAmount = categoryTxns.reduce((sum, txn) => sum + txn.amount, 0);
        const avgAmount = totalAmount / categoryTxns.length;
        const netAmount = categoryTxns.reduce((sum, txn) => sum + (txn.net_amount || txn.amount), 0);

        const modalHTML = `
                <div class="modal-overlay active" id="transactionModal" onclick="closeModalOnOverlay(event)">
                    <div class="modal-content" onclick="event.stopPropagation()">
                        <div class="modal-header">
                            <div class="modal-title">
                                <span>${categoryName}</span>
                                <span class="modal-category-badge">${categoryTxns.length} transactions</span>
                            </div>
                            <button class="modal-close" onclick="closeTransactionModal()">×</button>
                        </div>
                        <div class="modal-body">
                            <div class="modal-summary">
                                <div class="modal-summary-item">
                                    <div class="modal-summary-label">Total Spent</div>
                                    <div class="modal-summary-value">₹${totalAmount.toLocaleString('en-IN', {maximumFractionDigits: 0})}</div>
                                </div>
                                <div class="modal-summary-item">
                                    <div class="modal-summary-label">Average</div>
                                    <div class="modal-summary-value">₹${avgAmount.toLocaleString('en-IN', {maximumFractionDigits: 0})}</div>
                                </div>
                                <div class="modal-summary-item">
                                    <div class="modal-summary-label">Net (After Reimb.)</div>
                                    <div class="modal-summary-value">₹${netAmount.toLocaleString('en-IN', {maximumFractionDigits: 0})}</div>
                                </div>
                            </div>
                            <div class="transaction-list">
                                ${categoryTxns.map(txn => renderTransaction(txn)).join('')}
                            </div>
                        </div>
                    </div>
                </div>
            `;

        const existingModal = document.getElementById('transactionModal');
        if (existingModal) {
            existingModal.remove();
        }

        document.body.insertAdjacentHTML('beforeend', modalHTML);
        document.body.style.overflow = 'hidden';
    }

    // Update the renderTransaction function to include edit button

    function renderTransaction(txn) {
        const date = new Date(txn.date);
        const dateStr = date.toLocaleDateString('en-IN', {
            day: '2-digit', month: 'short', year: 'numeric'
        });

        const entityIcon = txn.entity_type === 'person' ? '👤' :
            txn.entity_type === 'platform' ? '🏢' :
                txn.entity_type === 'merchant' ? '🏪' : '';

        return `
        <div class="transaction-item" data-txn-id="${txn.txn_id}">
            <div class="transaction-header">
                <div class="transaction-merchant">${entityIcon} ${txn.merchant || 'Unknown'}</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="transaction-amount">₹${txn.amount.toLocaleString('en-IN', {maximumFractionDigits: 0})}</div>
                    <button class="edit-btn" onclick="editTransaction('${txn.txn_id}', '${txn.category}', '${txn.merchant}')">⋮</button>
                </div>
            </div>
            <div class="transaction-details">
                <span class="transaction-date">📅 ${dateStr}</span>
                <span style="color: var(--text-muted); font-size: 13px;">
                    ${txn.description ? txn.description.substring(0, 40) : ''}
                </span>
            </div>
        </div>
    `;
    }

    // Edit transaction function
    function editTransaction(txnId, currentCategory, merchantName) {
        const categories = [
            'Food & Dining',
            'Shopping',
            'Transport',
            'Utilities',
            'Entertainment',
            'Healthcare',
            'Transfer / P2P',
            'Rent',
            'Education',
            'ATM / Cash',
            'Other'
        ];

        // Build dropdown options
        const options = categories.map(cat =>
            `<option value="${cat}" ${cat === currentCategory ? 'selected' : ''}>${cat}</option>`
        ).join('');

        // Create inline edit UI
        const txnElement = document.querySelector(`[data-txn-id="${txnId}"]`);
        if (!txnElement) return;

        const editHTML = `
        <div class="edit-container">
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
                <select id="edit-category-${txnId}" class="category-dropdown">
                    ${options}
                </select>
                <button onclick="saveCorrection('${txnId}')" class="save-btn">Save</button>
                <button onclick="cancelEdit('${txnId}')" class="cancel-btn">✕</button>
            </div>
        </div>
    `;

        // Append edit UI
        txnElement.innerHTML += editHTML;
    }

    // Save correction
    async function saveCorrection(txnId) {
        const dropdown = document.getElementById(`edit-category-${txnId}`);
        const newCategory = dropdown.value;

        try {
            const response = await fetch('/api/transactions/correct', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    txn_id: txnId,
                    new_category: newCategory
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                // Show success message
                showNotification(`✅ Updated! ${result.updated_count} transaction(s) recategorized.`);

                // Reload dashboard after 1 second
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showNotification('❌ Error: ' + result.message);
            }
        } catch (error) {
            showNotification('❌ Failed to save correction');
            console.error(error);
        }
    }

    // Cancel edit
    function cancelEdit(txnId) {
        const editContainer = document.querySelector(`[data-txn-id="${txnId}"] .edit-container`);
        if (editContainer) {
            editContainer.remove();
        }
    }

    // Show notification
    function showNotification(message) {
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #2d2d2d;
    color: #ffffff;
    padding: 12px 20px;
    border-radius: 8px;
    border: 1px solid #00b8a3;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 10000;
    animation: slideIn 0.3s ease;
`;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
</script>
<script>
    function closeTransactionModal() {
        const modal = document.getElementById('transactionModal');
        if (modal) {
            modal.classList.remove('active');
            setTimeout(() => modal.remove(), 200);
        }
        document.body.style.overflow = 'auto';
    }

    function closeModalOnOverlay(event) {
        if (event.target.id === 'transactionModal') {
            closeTransactionModal();
        }
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeTransactionModal();
        }
    });

    function makeCategoryTableClickable() {
        const tableBody = document.getElementById('categoryTableBody');
        if (!tableBody) return;

        const rows = tableBody.getElementsByTagName('tr');
        for (let row of rows) {
            row.style.cursor = 'pointer';
            row.addEventListener('click', function () {
                const categoryCell = this.getElementsByTagName('td')[0];
                if (categoryCell) {
                    const categoryName = categoryCell.querySelector('strong')?.textContent ||
                        categoryCell.textContent.trim();
                    showCategoryTransactions(categoryName);
                }
            });
        }
    }

    function makePieChartClickable() {
        const pieChart = document.getElementById('pieChart');
        if (!pieChart) return;

        pieChart.on('plotly_click', function (data) {
            const point = data.points[0];
            const categoryName = point.label;
            showCategoryTransactions(categoryName);
        });
    }

    function fetchTransactions() {
        fetch('/api/transactions/classified')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    allTransactions = data.transactions;
                    console.log(`Loaded ${allTransactions.length} transactions for drill-down`);
                }
            })
            .catch(error => {
                console.log('Transactions not yet available:', error);
            });
    }

    window.addEventListener('load', function () {
        fetchTransactions();

        fetch('/api/dashboard-data')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success' && data.data) {
                    updateDashboard(data.data);
                }
            })
            .catch(error => console.log('No existing data'));

        setTimeout(() => {
            makeCategoryTableClickable();
            makePieChartClickable();
        }, 1000);
    });
    // ========================================
    // COLLAPSIBLE SECTIONS
    // ========================================

    function toggleSection(sectionId) {
        const section = document.getElementById(sectionId);
        if (section) {
            section.classList.toggle('expanded');

// Save state to localStorage
            const isExpanded = section.classList.contains('expanded');
            localStorage.setItem(`section_${sectionId}`, isExpanded);
        }
    }

    // Auto-expand sections based on saved state
    function restoreSectionStates() {
        const sections = document.querySelectorAll('.collapsible-section');
        sections.forEach(section => {
            const sectionId = section.id;
            const savedState = localStorage.getItem(`section_${sectionId}`);
            if (savedState === 'true') {
                section.classList.add('expanded');
            }
        });
    }

    // Call on page load
    window.addEventListener('load', restoreSectionStates);
</script>
