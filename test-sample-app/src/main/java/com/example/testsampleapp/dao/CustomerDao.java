package com.example.testsampleapp.dao;

import com.example.testsampleapp.model.Customer;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CustomerDao {
    Customer findById(Integer id);
}
