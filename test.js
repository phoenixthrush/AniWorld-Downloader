// Test file
document.addEventListener('DOMContentLoaded', function () {
    const keepUpdatedCheckbox = document.getElementById('keep-updated-checkbox');
    const pathCustom = document.getElementById('path-custom');
    const customPathGroup = document.getElementById('custom-path-group');

    if (pathCustom) {
        pathCustom.addEventListener('change', function () {
            if (customPathGroup && this.checked) {
                customPathGroup.style.display = 'block';
            }
        });
    }

    console.log('Test OK');
});
