package com.example.sampleapp.service;

import com.example.sampleapp.dao.ProductDao;
import com.example.sampleapp.model.Product;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class ProductServiceImpl implements ProductService {

    @Autowired
    private ProductDao productDao;

    @Override
    public List<Product> getAllProducts() {
        return productDao.findAll();
    }

    @Override
    public List<Product> getProductsByCategory(String category) {
        return productDao.findByCategory(category);
    }

    @Override
    public Product getProductById(Integer id) {
        return productDao.findById(id);
    }

    @Override
    @Transactional
    public void createProduct(Product product) {
        productDao.insert(product);
    }

    @Override
    @Transactional
    public void updateProduct(Product product) {
        productDao.update(product);
    }

    @Override
    @Transactional
    public void deleteProduct(Integer id) {
        productDao.delete(id);
    }

    @Override
    public boolean checkStock(Integer id, Integer requiredQuantity) {
        Product product = productDao.findById(id);
        return product != null && product.getStock() >= requiredQuantity;
    }

    @Override
    @Transactional
    public void decreaseStock(Integer id, Integer quantity) {
        productDao.updateStock(id, -quantity);
    }
}
