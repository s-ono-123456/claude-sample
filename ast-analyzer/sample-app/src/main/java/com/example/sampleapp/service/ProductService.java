package com.example.sampleapp.service;

import com.example.sampleapp.model.Product;
import java.util.List;

public interface ProductService {
    List<Product> getAllProducts();
    List<Product> getProductsByCategory(String category);
    Product getProductById(Integer id);
    void createProduct(Product product);
    void updateProduct(Product product);
    void deleteProduct(Integer id);
    boolean checkStock(Integer id, Integer requiredQuantity);
    void decreaseStock(Integer id, Integer quantity);
}
