import { state } from './state.js';
import * as dom from './dom.js';
import { closePlusMenus } from './layout.js';

const { btnAttach, btnAttachImage, expandedImg, fileInput, imagePreviewContainer, inputText, modal } = dom;

    if (btnAttach) {
        btnAttach.addEventListener('click', () => {
            fileInput.click();
        });
    }

    if (btnAttachImage) {
        btnAttachImage.addEventListener('click', () => {
            closePlusMenus();
            fileInput.click();
        });
    }

    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        for (let i = 0; i < files.length; i++) {
            addImage(files[i]);
        }
        fileInput.value = '';
    });

    inputText.addEventListener('paste', (e) => {
        const clipboardData = e.clipboardData || window.clipboardData;
        if (!clipboardData) return;
        let imagePasted = false;
        for (let i = 0; i < clipboardData.items.length; i++) {
            const item = clipboardData.items[i];
            if (item.type.indexOf('image/') !== -1) {
                imagePasted = true;
                e.preventDefault();
                const file = item.getAsFile();
                if (file) {
                    addImage(file);
                }
            }
        }
        if (imagePasted) {
            setTimeout(() => {
                if (inputText.value.length > 500 && !inputText.value.includes(' ')) {
                    inputText.value = '';
                    inputText.style.height = 'auto';
                }
            }, 10);
        }
    });

    window.expandImage = function(src) {
        expandedImg.src = src;
        modal.classList.remove('hidden');
    };
    function renderImagePreviews() {
        imagePreviewContainer.innerHTML = '';
        if (state.attachedImages.length === 0) {
            imagePreviewContainer.classList.add('hidden');
            return;
        }
        imagePreviewContainer.classList.remove('hidden');
        state.attachedImages.forEach((img, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'relative inline-block w-20 h-20 group';
            const imgEl = document.createElement('img');
            imgEl.className = 'w-full h-full object-cover rounded-lg border border-[var(--border-suave)]';
            imgEl.src = img.dataUrl;
            imgEl.title = img.name;
            const btnRemove = document.createElement('button');
            btnRemove.className = 'absolute -top-2 -right-2 bg-[var(--perigo)] text-[var(--text-branco)] rounded-full w-5 h-5 flex items-center justify-center text-xs hover:bg-[var(--vermelho-excluir-hover)] focus:outline-none opacity-0 group-hover:opacity-100 transition-opacity';
            btnRemove.innerHTML = '✕';
            btnRemove.onclick = () => {
                state.attachedImages.splice(index, 1);
                renderImagePreviews();
            };
            wrapper.appendChild(imgEl);
            wrapper.appendChild(btnRemove);
            imagePreviewContainer.appendChild(wrapper);
        });
    }

    function addImage(file) {
        if (!file || !file.type || !file.type.startsWith('image/')) return;
        const reader = new FileReader();
        reader.onload = (readerEvent) => {
            const dataUrl = readerEvent.target.result;
            const base64 = dataUrl.split(',')[1];
            const mime = (dataUrl.match(/^data:([^;]+);/) || [])[1] || 'image/png';
            const name = file.name || `imagem${state.imageCounter++}`;
            state.attachedImages.push({ base64, dataUrl, name, mime });
            renderImagePreviews();
        };
        reader.readAsDataURL(file);
    }

export { renderImagePreviews, addImage };
