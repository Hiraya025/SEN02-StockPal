let allItems = [];

// Centralized fetch wrapper to handle 401 Unauthorized globally
async function apiFetch(url, options = {}) {
    const token = localStorage.getItem('token');
    const headers = new Headers(options.headers || {});
    
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    
    if (!headers.has('Content-Type') && options.body instanceof URLSearchParams === false) {
        headers.set('Content-Type', 'application/json');
    }

    options.headers = headers;

    const response = await fetch(url, options);
    
    if (response.status === 401) {
        localStorage.removeItem('token');
        document.getElementById('loginPage').classList.remove('d-none');
        document.getElementById('appContainer').classList.add('d-none');
        throw new Error("Session expired or unauthorized. Please log in again.");
    }
    
    return response;
}

// --- View Navigation ---
function showView(viewId) {
    document.getElementById('dashboardView').classList.toggle('d-none', viewId !== 'dashboardView');
    document.getElementById('movementView').classList.toggle('d-none', viewId !== 'movementView');

    const navDashboard = document.getElementById('navDashboard');
    const navMovements = document.getElementById('navMovements');
    
    if (viewId === 'dashboardView') {
        navDashboard.className = "nav-link active bg-light rounded-3 text-primary fw-bold p-3";
        navMovements.className = "nav-link text-muted p-3";
        fetchInventory();
    } else {
        navMovements.className = "nav-link active bg-light rounded-3 text-primary fw-bold p-3";
        navDashboard.className = "nav-link text-muted p-3";
        fetchMovements();
    }
}

// --- Auth & Role Based Access ---
function getUserRole() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        
        const parsed = JSON.parse(jsonPayload);
        // FIX: Look for role in the root claims first, then fallback to sub
        return parsed.role || (parsed.sub ? parsed.sub.role : null);
    } catch (e) { return null; }
}

function applyRoleBasedAccess() {
    const role = getUserRole();
    document.getElementById('roleDisplay').textContent = role === 'admin' ? 'Manager Role' : 'Employee Role';
    
    const addItemBtn = document.getElementById('addItemBtn');
    const deleteButtons = document.querySelectorAll('.delete-btn');

    if (role !== 'admin') {
        if (addItemBtn) addItemBtn.style.display = 'none';
        deleteButtons.forEach(btn => btn.style.display = 'none');
    } else {
        if (addItemBtn) addItemBtn.style.display = 'block';
        deleteButtons.forEach(btn => btn.style.display = 'inline-block');
    }
}

async function handleLogin(event) {
    event.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorText = document.getElementById('loginError');

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('token', data.access_token);
            
            // Switch views
            document.getElementById('loginPage').classList.add('d-none');
            document.getElementById('appContainer').classList.remove('d-none');
            
            document.getElementById('userDisplay').textContent = username;
            
            applyRoleBasedAccess(); 
            fetchInventory();
        } else {
            errorText.textContent = 'Invalid credentials.';
            errorText.classList.remove('d-none');
        }
    } catch (error) {
        errorText.textContent = 'Backend connection failed.';
        errorText.classList.remove('d-none');
    }
}

// --- Inventory Logic ---
async function fetchInventory() {
    const token = localStorage.getItem('token');
    
    if (!token) {
        document.getElementById('loginPage').classList.remove('d-none');
        document.getElementById('appContainer').classList.add('d-none');
        return;
    }

    // Ensure dashboard is visible if token exists on load
    document.getElementById('loginPage').classList.add('d-none');
    document.getElementById('appContainer').classList.remove('d-none');

    try {
        const response = await apiFetch('/api/inventory');
        allItems = await response.json();
        
        const select = document.getElementById('categoryFilter');
        if (select.options.length === 1) {
            const categories = [...new Set(allItems.map(i => i.category).filter(Boolean))];
            categories.forEach(cat => {
                select.innerHTML += `<option value="${cat}">${cat}</option>`;
            });
        }
        renderInventoryTable(allItems);
    } catch (error) { console.error("Backend Error:", error); }
}

function filterInventory() {
    const search = document.getElementById('inventorySearch').value.toLowerCase();
    const filterCat = document.getElementById('categoryFilter').value;

    const filtered = allItems.filter(item => {
        const matchesSearch = item.sku.toLowerCase().includes(search) || item.item_name.toLowerCase().includes(search);
        const matchesCat = filterCat === '' || item.category === filterCat;
        return matchesSearch && matchesCat;
    });
    renderInventoryTable(filtered);
}

function renderInventoryTable(data) {
    const tableBody = document.getElementById('inventory-table-body');
    tableBody.innerHTML = '';

    data.forEach(item => {
        const badge = item.is_low_stock ? 'badge-low' : 'badge-ok';
        const label = item.is_low_stock ? 'Low Stock' : 'Optimal';
        const cat = item.category || '-';

        tableBody.innerHTML += `
            <tr>
                <td class="ps-4">
                    <div class="fw-bold text-dark">${item.item_name}</div>
                    <div class="small text-muted">${item.sku}</div>
                </td>
                <td><span class="text-muted small">${cat}</span></td>
                <td><span class="fw-bold">${item.current_stock}</span> <small class='text-muted'>/ ${item.min_threshold}</small></td>
                <td><span class="badge ${badge} px-3 py-2 rounded-pill">${label}</span></td>
                <td class="text-end pe-4">
                    <div class="btn-group gap-1">
                        <button onclick="prepMove('${item.sku}', 'stock-in')" class="btn btn-sm btn-outline-success border-0" title="Stock In"><i class="fas fa-plus"></i></button>
                        <button onclick="prepMove('${item.sku}', 'stock-out')" class="btn btn-sm btn-outline-danger border-0" title="Stock Out"><i class="fas fa-minus"></i></button>
                        <button onclick="prepEdit('${item.sku}', '${item.item_name}', ${item.min_threshold})" class="btn btn-sm btn-light border-0" title="Edit"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteItem('${item.sku}')" class="delete-btn btn btn-sm btn-light border-0 text-danger" title="Delete"><i class="fas fa-trash"></i></button>
                    </div>
                </td>
            </tr>`;
    });
    applyRoleBasedAccess();
}

async function submitNewItem(e) {
    e.preventDefault();
    const payload = {
        sku: document.getElementById('skuInput').value,
        item_name: document.getElementById('nameInput').value,
        category: document.getElementById('catInput').value,
        current_stock: parseInt(document.getElementById('stockInput').value),
        min_threshold: parseInt(document.getElementById('minInput').value)
    };

    try {
        const response = await apiFetch('/api/inventory', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('addModal')).hide();
            document.getElementById('addForm').reset();
            fetchInventory();
        }
    } catch (error) { console.error(error); }
}

function prepEdit(sku, name, min) {
    document.getElementById('editSku').value = sku;
    document.getElementById('editName').value = name;
    document.getElementById('editMin').value = min;
    new bootstrap.Modal(document.getElementById('editModal')).show();
}

async function updateItem(e) {
    e.preventDefault();
    const sku = document.getElementById('editSku').value;
    const payload = {
        item_name: document.getElementById('editName').value,
        min_threshold: parseInt(document.getElementById('editMin').value)
    };

    try {
        const response = await apiFetch(`/api/inventory/${sku}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('editModal')).hide();
            fetchInventory();
        }
    } catch (error) { console.error(error); }
}

async function deleteItem(sku) {
    if (!confirm(`Permanently delete ${sku}?`)) return;
    try {
        const response = await apiFetch(`/api/inventory/${sku}`, { 
            method: 'DELETE'
        });
        if (response.ok) fetchInventory();
    } catch (error) { console.error(error); }
}

// --- Stock Movement Logs ---
function prepMove(sku, type) {
    document.getElementById('moveSku').value = sku;
    document.getElementById('moveType').value = type;
    document.getElementById('moveTitle').innerText = type === 'stock-in' ? 'Record Stock-In' : 'Record Stock-Out';
    const btn = document.getElementById('moveSubmitBtn');
    btn.className = type === 'stock-in' ? 'btn btn-success w-100 py-2' : 'btn btn-danger w-100 py-2';
    new bootstrap.Modal(document.getElementById('movementModal')).show();
}

async function submitMovement(e) {
    e.preventDefault();
    const sku = document.getElementById('moveSku').value;
    
    const payload = {
        movement_type: document.getElementById('moveType').value,
        quantity_changed: parseInt(document.getElementById('moveQty').value)
    };

    try {
        const response = await apiFetch(`/api/inventory/${sku}/movement`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('movementModal')).hide();
            document.getElementById('moveForm').reset();
            fetchInventory();
        } else {
            const data = await response.json();
            alert(data.error);
        }
    } catch (error) { console.error(error); }
}

async function fetchMovements() {
    try {
        const response = await apiFetch('/api/movements');
        const data = await response.json();
        const tbody = document.getElementById('movements-table-body');
        tbody.innerHTML = '';

        data.forEach(m => {
            const badgeClass = m.movement_type === 'stock-in' ? 'bg-success bg-opacity-10 text-success' : 'bg-danger bg-opacity-10 text-danger';
            tbody.innerHTML += `
                <tr>
                    <td class="ps-4 text-muted small">${new Date(m.timestamp).toLocaleString()}</td>
                    <td class="fw-bold">${m.sku}</td>
                    <td>${m.item_name || 'N/A'}</td>
                    <td class="text-muted">${m.username || 'System'}</td>
                    <td><span class="px-2 py-1 rounded small fw-bold ${badgeClass}">${m.movement_type.toUpperCase()}</span></td>
                    <td class="fw-bold">${m.quantity_changed}</td>
                </tr>
            `;
        });
    } catch (error) { console.error(error); }
}

async function downloadReport() {
    try {
        const response = await apiFetch('/api/inventory/report');
        if (response.ok) {
            const blob = await response.blob();
            const a = document.createElement('a');
            a.href = window.URL.createObjectURL(blob);
            a.download = 'inventory_report.csv';
            a.click();
        }
    } catch (e) { console.error(e); }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    applyRoleBasedAccess();
    fetchInventory();
});
